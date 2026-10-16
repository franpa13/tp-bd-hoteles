#!/usr/bin/env python3
"""
Script 70: caché fría/caliente (Punto 23) y Parte IX — memoria, servidor y rendimiento (Puntos 43 a 48).
Requiere poder reiniciar el servidor y vaciar la caché del sistema operativo (root).
Ajustar PGCTL / PGDATA al entorno.
"""
import subprocess, time, statistics, re
import psycopg
from tp import *

PGCTL = "/usr/lib/postgresql/16/bin/pg_ctl"
PGDATA = "/var/lib/pgtp/data"
LOG = "/var/lib/pgtp/log"


def reiniciar(vaciar_cache_so=True):
    subprocess.run(["su", "postgres", "-c", f"{PGCTL} -D {PGDATA} -m fast restart -w -l {LOG} -o '-k /tmp -p 5432'"],
                   check=True, capture_output=True)
    if vaciar_cache_so:
        subprocess.run("sync; echo 3 > /proc/sys/vm/drop_caches", shell=True, check=True)
    time.sleep(1)


def sql_admin(s):
    with psycopg.connect(DSN, autocommit=True) as c:
        return c.execute(s).fetchall() if s.strip().upper().startswith(("SELECT", "SHOW")) else c.execute(s)


# ------------------------------------------------------------------ Punto 23
titulo("PUNTO 23 — Cold cache vs warm cache")
sql_admin("ALTER SYSTEM SET track_io_timing = on")
consultas = [
    ("Recorrido completo: count(*) de reserva", "SELECT count(*) FROM reserva"),
    ("Índice: reservas de 200 huéspedes", "SELECT count(*) FROM reserva WHERE huesped_id IN (SELECT g * 4999 FROM generate_series(1, 200) g)"),
    ("Agregación por mes 2024 (índice fecha)", "SELECT date_trunc('month', fecha_inicio), count(*) FROM reserva WHERE fecha_inicio >= '2024-01-01' AND fecha_inicio < '2025-01-01' GROUP BY 1"),
]
for et, q in consultas:
    reiniciar(True)
    c = conectar()
    tiempos = []
    for i in range(4):
        p = plan(c, q)
        r = resumen_plan(p)
        io = re.search(r"I/O Timings: ([^\n]+)", p)
        tiempos.append(r["ms"])
        estado = ["FRÍA (servidor reiniciado + caché del SO vaciada)", "caliente", "caliente", "caliente"][i]
        print(f"{et:45} ejec {i+1} [{estado:48}] {r['ms']:9.1f} ms | {r['buffers']} | IO: {io.group(1) if io else '-'}")
    c.close()
    print(f"   -> fría/caliente = x{tiempos[0]/statistics.median(tiempos[1:]):.1f}")
print("\n>> Fría sólo para PostgreSQL (reinicio SIN vaciar la caché del SO):")
reiniciar(False)
c = conectar()
for i in range(2):
    p = plan(c, consultas[0][1]); r = resumen_plan(p); io = re.search(r"I/O Timings: ([^\n]+)", p)
    print(f"   ejec {i+1}: {r['ms']:9.1f} ms | {r['buffers']} | IO: {io.group(1) if io else '-'}")
c.close()

# ------------------------------------------------------------------ Punto 43
titulo("PUNTO 43 — Configuración del servidor")
c = conectar()
print("config_file:", c.execute("SHOW config_file").fetchone()[0])
print("data_directory:", c.execute("SHOW data_directory").fetchone()[0])
print("postgresql.auto.conf contiene lo que se cambia con ALTER SYSTEM")
for r in c.execute("""SELECT name, setting, unit, source, context FROM pg_settings WHERE name IN
   ('shared_buffers','effective_cache_size','work_mem','maintenance_work_mem','hash_mem_multiplier','temp_buffers',
    'max_connections','superuser_reserved_connections','wal_buffers','max_wal_size','checkpoint_timeout',
    'checkpoint_completion_target','random_page_cost','seq_page_cost','effective_io_concurrency',
    'default_statistics_target','autovacuum','autovacuum_vacuum_scale_factor','join_collapse_limit',
    'from_collapse_limit','max_parallel_workers_per_gather','temp_file_limit','synchronous_commit','fsync',
    'huge_pages','track_io_timing','log_min_duration_statement','deadlock_timeout','lock_timeout','statement_timeout')
   ORDER BY name""").fetchall():
    print("  ", r)

print("\n>> work_mem: ordenamiento en memoria vs en disco")
q = "SELECT reserva_id FROM reserva WHERE fecha_inicio >= '2024-01-01' AND fecha_inicio < '2025-01-01' ORDER BY tarifa_noche, reserva_id"
for wm in ("4MB", "64MB"):
    c.execute(f"SET work_mem = '{wm}'")
    p = plan(c, q)
    metodo = re.search(r"Sort Method: ([^\n]+)", p)
    print(f"   work_mem={wm:5}: {resumen_plan(p)['ms']:8.1f} ms | {metodo.group(1) if metodo else ''}")
print(">> work_mem: Hash Join / HashAggregate")
q2 = "SELECT huesped_id, count(*) FROM reserva GROUP BY huesped_id ORDER BY 2 DESC LIMIT 5"
for wm in ("4MB", "256MB"):
    c.execute(f"SET work_mem = '{wm}'")
    p = plan(c, q2)
    bat = re.search(r"(Batches: \d+[^\n]*)", p)
    print(f"   work_mem={wm:6}: {resumen_plan(p)['ms']:8.1f} ms | {bat.group(1) if bat else re.findall(r'(HashAggregate|GroupAggregate|Sort Method: [^\n]+)', p)[:2]}")
c.execute("RESET work_mem")
print(">> maintenance_work_mem: CREATE INDEX")
for mwm in ("16MB", "512MB"):
    c.execute(f"SET maintenance_work_mem = '{mwm}'")
    t = time.perf_counter(); c.execute("CREATE INDEX ix_tmp_mwm ON reserva (fecha_fin)"); dt_ = time.perf_counter() - t
    c.execute("DROP INDEX ix_tmp_mwm")
    print(f"   maintenance_work_mem={mwm:6}: CREATE INDEX (fecha_fin) {dt_:5.1f} s")
c.close()

# ------------------------------------------------------------------ Punto 44
titulo("PUNTO 44 — shared_buffers (equivalente al InnoDB Buffer Pool)")
sql_admin("CREATE EXTENSION IF NOT EXISTS pg_buffercache")
q = "SELECT count(*), sum(tarifa_noche) FROM reserva"
for sb in ("128MB", "2GB"):
    sql_admin(f"ALTER SYSTEM SET shared_buffers = '{sb}'")
    reiniciar(True)
    c = conectar()
    c.execute("SET enable_indexonlyscan = off")
    filas = []
    for i in range(3):
        p = plan(c, q); r = resumen_plan(p)
        filas.append(r)
        print(f"shared_buffers={sb:5} ejec {i+1}: {r['ms']:8.1f} ms | {r['buffers']}")
    print("   contenido del buffer cache (top 5 relaciones):")
    for x in c.execute("""SELECT c.relname, count(*) AS buffers, pg_size_pretty(count(*)*8192) AS tam,
                                 round(100.0*count(*)/(SELECT setting::int FROM pg_settings WHERE name='shared_buffers'),1) AS pct
                            FROM pg_buffercache b JOIN pg_class c ON b.relfilenode = pg_relation_filenode(c.oid)
                           WHERE b.reldatabase = (SELECT oid FROM pg_database WHERE datname = current_database())
                           GROUP BY c.relname ORDER BY 2 DESC LIMIT 5""").fetchall():
        print("     ", x)
    print("   uso de páginas (usagecount):", c.execute("SELECT usagecount, count(*) FROM pg_buffercache GROUP BY 1 ORDER BY 1").fetchall())
    hit = c.execute("SELECT round(100.0*blks_hit/nullif(blks_hit+blks_read,0),2) FROM pg_stat_database WHERE datname='hoteles'").fetchone()[0]
    print(f"   tasa de aciertos en caché desde el reinicio: {hit} %")
    c.close()
sql_admin("ALTER SYSTEM SET shared_buffers = '1GB'")   # valor que queda para el resto de los experimentos
reiniciar(False)

# ------------------------------------------------------------------ Punto 45
titulo("PUNTO 45 — ¿CPU, disco o red?")
reiniciar(True)
c = conectar()
q_io = "SELECT count(*) FROM reserva WHERE observaciones IS NOT NULL"
p = plan(c, q_io); io = re.search(r"I/O Timings: ([^\n]+)", p)
print(f"DISCO (fría): {resumen_plan(p)['ms']:.0f} ms | {resumen_plan(p)['buffers']} | {io.group(1) if io else ''}")
p = plan(c, q_io); io = re.search(r"I/O Timings: ([^\n]+)", p)
print(f"misma, caliente: {resumen_plan(p)['ms']:.0f} ms | {resumen_plan(p)['buffers']} | {io.group(1) if io else '-'}")
q_cpu = ("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY tarifa_noche), "
         "count(DISTINCT md5(huesped_id::text || fecha_inicio::text)) FROM reserva WHERE fecha_inicio >= '2024-01-01' AND fecha_inicio < '2025-01-01'")
plan(c, q_cpu)
t_cpu0 = time.process_time()
p = plan(c, q_cpu); io = re.search(r"I/O Timings: ([^\n]+)", p)
print(f"CPU (caliente, md5 + percentil): {resumen_plan(p)['ms']:.0f} ms | {resumen_plan(p)['buffers']} | IO: {io.group(1) if io else 'ninguna'}")
pid = c.execute("SELECT pg_backend_pid()").fetchone()[0]
def cpu_backend():
    s = open(f"/proc/{pid}/stat").read().split()
    return (int(s[13]) + int(s[14])) / 100
cb0 = cpu_backend(); t = time.perf_counter(); c.execute(q_cpu).fetchall(); dt_ = time.perf_counter() - t; cb1 = cpu_backend()
print(f"   tiempo de pared {dt_:.2f} s | CPU usada por el proceso servidor {cb1-cb0:.2f} s -> {100*(cb1-cb0)/dt_:.0f} % de un núcleo")
print("RED / TRANSPORTE: mismo trabajo en el servidor, distinto volumen enviado al cliente")
for et, q in [("count(*) en el servidor (1 fila)", "SELECT count(*) FROM reserva WHERE fecha_inicio >= '2019-01-01' AND fecha_inicio < '2021-01-01'"),
              ("traer 1,2 M filas, 2 columnas", "SELECT reserva_id, fecha_inicio FROM reserva WHERE fecha_inicio >= '2019-01-01' AND fecha_inicio < '2021-01-01'"),
              ("traer 1,2 M filas, SELECT *", "SELECT * FROM reserva WHERE fecha_inicio >= '2019-01-01' AND fecha_inicio < '2021-01-01'")]:
    srv = resumen_plan(plan(c, q))["ms"]
    t = time.perf_counter(); cur = c.execute(q); filas = cur.fetchall(); dt_ = (time.perf_counter() - t) * 1000
    bytes_ = sum(len(str(v)) for f in filas[:20000] for v in f) * len(filas) / max(1, min(len(filas), 20000))
    print(f"   {et:35} servidor {srv:8.0f} ms | cliente {dt_:8.0f} ms | filas {len(filas):9,} | ~{bytes_/1e6:6.1f} MB de texto")
print("Ida y vuelta (round trips): 1.000 consultas de 1 fila vs 1 consulta de 1.000 filas")
t = time.perf_counter()
for i in range(1, 1001):
    c.execute("SELECT * FROM reserva WHERE reserva_id = %s", (i * 7000,)).fetchall()
a = (time.perf_counter() - t) * 1000
t = time.perf_counter(); c.execute("SELECT * FROM reserva WHERE reserva_id = ANY(%s)", ([i * 7000 for i in range(1, 1001)],)).fetchall(); b = (time.perf_counter() - t) * 1000
print(f"   1.000 consultas: {a:.0f} ms | 1 consulta con ANY(): {b:.0f} ms")
with psycopg.connect("host=127.0.0.1 user=postgres dbname=hoteles", autocommit=True) as ctcp:
    t = time.perf_counter()
    for i in range(1, 1001):
        ctcp.execute("SELECT * FROM hotel.reserva WHERE reserva_id = %s", (i * 7000,)).fetchall()
    print(f"   1.000 consultas por TCP (localhost) en lugar de socket Unix: {(time.perf_counter()-t)*1000:.0f} ms")
c.close()

# ------------------------------------------------------------------ Punto 46
titulo("PUNTO 46 — Costo de conexión y pool de conexiones")
ts = []
for _ in range(100):
    t = time.perf_counter(); x = psycopg.connect(DSN); x.close(); ts.append((time.perf_counter() - t) * 1000)
print(f"abrir+cerrar conexión (socket Unix): mediana {statistics.median(ts):.2f} ms")
ts = []
for _ in range(100):
    t = time.perf_counter(); x = psycopg.connect("host=127.0.0.1 user=postgres dbname=hoteles"); x.close(); ts.append((time.perf_counter() - t) * 1000)
print(f"abrir+cerrar conexión (TCP localhost): mediana {statistics.median(ts):.2f} ms")
open("/tmp/pgbench_reserva.sql", "w").write("\\set id random(1, 7000000)\nSELECT * FROM hotel.reserva WHERE reserva_id = :id;\n")
for clientes in (1, 8, 32):
    for flag, et in (("", "conexión persistente (pool)"), ("-C", "nueva conexión por transacción")):
        out = subprocess.run(f"pgbench -h /tmp -U postgres -n -f /tmp/pgbench_reserva.sql -c {clientes} -j 2 -T 10 {flag} hoteles",
                             shell=True, capture_output=True, text=True).stdout
        tps = re.search(r"tps = ([\d.]+)", out); lat = re.search(r"latency average = ([\d.]+) ms", out)
        print(f"   clientes={clientes:2} {et:32} tps={float(tps.group(1)):9.0f} | latencia media {lat.group(1) if lat else '?'} ms")
print("pool en la aplicación (psycopg_pool) vs conexión por pedido, 2.000 pedidos con 8 hilos:")
from concurrent.futures import ThreadPoolExecutor
from psycopg_pool import ConnectionPool
def sin_pool(i):
    with psycopg.connect(DSN) as x:
        x.execute("SELECT * FROM reserva WHERE reserva_id = %s", (i * 3001,)).fetchall()
t = time.perf_counter()
with ThreadPoolExecutor(8) as ex: list(ex.map(sin_pool, range(2000)))
a = time.perf_counter() - t
pool = ConnectionPool(DSN, min_size=8, max_size=8, open=True); pool.wait()
def con_pool(i):
    with pool.connection() as x:
        x.execute("SELECT * FROM reserva WHERE reserva_id = %s", (i * 3001,)).fetchall()
t = time.perf_counter()
with ThreadPoolExecutor(8) as ex: list(ex.map(con_pool, range(2000)))
b = time.perf_counter() - t; pool.close()
print(f"   sin pool: {a:.2f} s ({2000/a:.0f} pedidos/s) | con pool de 8: {b:.2f} s ({2000/b:.0f} pedidos/s)")

# ------------------------------------------------------------------ Punto 47
titulo("PUNTO 47 — Slow query log, auto_explain y pg_stat_statements")
sql_admin("ALTER SYSTEM SET shared_preload_libraries = pg_stat_statements, auto_explain")
sql_admin("ALTER SYSTEM SET log_min_duration_statement = '500ms'")
sql_admin("ALTER SYSTEM SET auto_explain.log_min_duration = '500ms'")
sql_admin("ALTER SYSTEM SET auto_explain.log_analyze = on")
sql_admin("ALTER SYSTEM SET log_lock_waits = on")
reiniciar(False)
sql_admin("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
sql_admin("SELECT pg_stat_statements_reset()")
inicio_log = sum(1 for _ in open(LOG, errors="ignore"))
c = conectar()
carga = [
    "SELECT count(*) FROM reserva WHERE extract(year FROM fecha_inicio) = 2023",
    "SELECT count(*) FROM huesped_email WHERE email LIKE '%rojas%'",
    "SELECT huesped_id, count(*) FROM reserva GROUP BY huesped_id ORDER BY 2 DESC LIMIT 10",
    "SELECT * FROM reserva WHERE reserva_id = 4000000",
    "SELECT count(*) FROM reserva WHERE fecha_inicio >= '2025-03-01' AND fecha_inicio < '2025-03-08'",
]
for _ in range(3):
    for q in carga:
        c.execute(q).fetchall()
for i in range(500):
    c.execute("SELECT * FROM reserva WHERE reserva_id = %s", (i * 10007,)).fetchall()
time.sleep(1)
lineas = open(LOG, errors="ignore").read().splitlines()[inicio_log:]
lentas = [l for l in lineas if "duration:" in l and "statement:" in l]
print(f"líneas del log con 'duration' (> 500 ms): {len(lentas)}")
for l in lentas[:6]:
    print("   ", l[:200])
plan_ae = [i for i, l in enumerate(lineas) if "Query Text" in l or "plan:" in l]
if plan_ae:
    print("Ejemplo de auto_explain en el log:")
    i0 = plan_ae[0]
    for l in lineas[i0:i0 + 14]:
        print("   ", l[:160])
print("\npg_stat_statements — top 5 por tiempo total:")
for r in c.execute("""SELECT calls, round(total_exec_time::numeric) AS total_ms, round(mean_exec_time::numeric,1) AS media_ms,
                             rows, shared_blks_hit, shared_blks_read, left(regexp_replace(query, '\\s+', ' ', 'g'), 80)
                        FROM pg_stat_statements WHERE dbid = (SELECT oid FROM pg_database WHERE datname='hoteles')
                       ORDER BY total_exec_time DESC LIMIT 5""").fetchall():
    print("   ", r)
c.close()

# ------------------------------------------------------------------ Punto 48
titulo("PUNTO 48 — Mantenimiento: VACUUM, ANALYZE, REINDEX y bloat")
c = conectar()
c.execute("CREATE EXTENSION IF NOT EXISTS pgstattuple")
c.execute("DROP TABLE IF EXISTS r_mant")
c.execute("CREATE TABLE r_mant WITH (autovacuum_enabled = off) AS SELECT * FROM reserva WHERE reserva_id <= 1000000")
c.execute("ALTER TABLE r_mant ADD PRIMARY KEY (reserva_id)")
c.execute("CREATE INDEX ix_mant_fecha ON r_mant (fecha_inicio)")
c.execute("CREATE INDEX ix_mant_tarifa ON r_mant (tarifa_noche)")
def estado_tabla(et):
    s = c.execute("SELECT table_len, tuple_count, dead_tuple_count, round(dead_tuple_percent::numeric,1), round(free_percent::numeric,1) FROM pgstattuple('r_mant')").fetchone()
    i = c.execute("SELECT round(avg_leaf_density::numeric,1), leaf_fragmentation FROM pgstatindex('ix_mant_tarifa')").fetchone()
    print(f"{et:42} tabla {s[0]/1e6:6.1f} MB | vivas {s[1]:8,} | muertas {s[2]:8,} ({s[3]}%) | libre {s[4]}% | índice tarifa {tam(c,'ix_mant_tarifa')[0]:>7} densidad hojas {i[0]}%")
estado_tabla("Recién creada")
t = time.perf_counter(); c.execute("UPDATE r_mant SET tarifa_noche = tarifa_noche * 1.1 WHERE reserva_id % 3 = 0"); print(f"UPDATE de 1/3 de las filas: {time.perf_counter()-t:.1f} s")
estado_tabla("Tras UPDATE masivo (sin VACUUM)")
print("   estimación del optimizador antes de ANALYZE:", c.execute("SELECT n_live_tup, n_dead_tup, last_vacuum, last_autovacuum, last_analyze FROM pg_stat_user_tables WHERE relname='r_mant'").fetchone())
t = time.perf_counter(); c.execute("VACUUM (VERBOSE OFF) r_mant"); print(f"VACUUM: {time.perf_counter()-t:.1f} s")
estado_tabla("Tras VACUUM")
t = time.perf_counter(); c.execute("REINDEX INDEX ix_mant_tarifa"); print(f"REINDEX ix_mant_tarifa: {time.perf_counter()-t:.1f} s")
estado_tabla("Tras REINDEX")
t = time.perf_counter(); c.execute("VACUUM FULL r_mant"); print(f"VACUUM FULL (reescribe tabla e índices, bloqueo exclusivo): {time.perf_counter()-t:.1f} s")
estado_tabla("Tras VACUUM FULL")
c.execute("DROP TABLE r_mant")
print("\nautovacuum en reserva:", c.execute("SELECT n_live_tup, n_dead_tup, last_autovacuum, last_autoanalyze, autovacuum_count, autoanalyze_count FROM pg_stat_user_tables WHERE relname='reserva'").fetchone())
print("umbral autovacuum para reserva = 50 + 0.2 * reltuples =",
      c.execute("SELECT (50 + 0.2*reltuples)::bigint FROM pg_class WHERE relname='reserva'").fetchone()[0], "filas muertas")
print("edad de transacciones (wraparound):", c.execute("SELECT datname, age(datfrozenxid) FROM pg_database WHERE datname='hoteles'").fetchone())
c.close()
print("\nFIN")
