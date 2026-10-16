#!/usr/bin/env python3
"""
Script 71 (complemento de 70): caché fría/caliente (Punto 23) y Parte IX — memoria, servidor y rendimiento (Puntos 43 a 48).
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


titulo("Complemento de 70_servidor.py: Puntos 44 (corregido), 47 y 48")
# ------------------------------------------------------------------ Punto 44
titulo("PUNTO 44 — shared_buffers (equivalente al InnoDB Buffer Pool)")
sql_admin("CREATE EXTENSION IF NOT EXISTS pg_buffercache")
q = "SELECT count(*), sum(tarifa_noche) FROM reserva"
q_al = "SELECT count(*), sum(tarifa_noche) FROM reserva WHERE reserva_id = ANY(%s)"
ids = [((i * 2654435761) % 7535000) + 1 for i in range(1, 60001)]   # 60.000 reservas dispersas
for sb in ("128MB", "2GB"):
    sql_admin(f"ALTER SYSTEM SET shared_buffers = '{sb}'")
    reiniciar(True)
    c = conectar()
    c.execute("SET enable_indexonlyscan = off")
    filas = []
    for i in range(3):
        p = plan(c, q); r = resumen_plan(p)
        filas.append(r)
        print(f"shared_buffers={sb:5} Seq Scan ejec {i+1}: {r['ms']:8.1f} ms | {r['buffers']}")
    for i in range(3):
        p = plan(c, q_al, (ids,)); r = resumen_plan(p)
        print(f"shared_buffers={sb:5} 60.000 lecturas por PK dispersas, ejec {i+1}: {r['ms']:8.1f} ms | {r['buffers']}")
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

# ------------------------------------------------------------------ Punto 47
titulo("PUNTO 47 — Slow query log, auto_explain y pg_stat_statements")
sql_admin("ALTER SYSTEM SET shared_preload_libraries = pg_stat_statements, auto_explain")
reiniciar(False)   # las librerías se cargan al iniciar; recién entonces existen sus parámetros
sql_admin("ALTER SYSTEM SET log_min_duration_statement = '500ms'")
sql_admin("ALTER SYSTEM SET auto_explain.log_min_duration = '500ms'")
sql_admin("ALTER SYSTEM SET auto_explain.log_analyze = on")
sql_admin("ALTER SYSTEM SET log_lock_waits = on")
sql_admin("SELECT pg_reload_conf()")
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
