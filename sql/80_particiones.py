#!/usr/bin/env python3
"""Script 80: Parte X — particionamiento, partition pruning y vistas materializadas (Puntos 50 a 52)."""
import re, time
from tp import *

c = conectar()

# ------------------------------------------------------------------ Punto 50
titulo("PUNTO 50 — Tabla particionada por año de fecha_inicio vs tabla sin particionar")
c.execute("DROP TABLE IF EXISTS reserva_part CASCADE")
c.execute("""CREATE TABLE reserva_part (LIKE reserva INCLUDING DEFAULTS)
             PARTITION BY RANGE (fecha_inicio)""")
c.execute("ALTER TABLE reserva_part ALTER COLUMN reserva_id DROP IDENTITY IF EXISTS")
for y in range(2015, 2028):
    c.execute(f"CREATE TABLE reserva_p{y} PARTITION OF reserva_part FOR VALUES FROM ('{y}-01-01') TO ('{y+1}-01-01')")
c.execute("CREATE TABLE reserva_pdef PARTITION OF reserva_part DEFAULT")

print(">> Intento de crear la restricción EXCLUDE sobre la tabla particionada:")
try:
    c.execute("""ALTER TABLE reserva_part ADD CONSTRAINT ex_part EXCLUDE USING gist
                 (habitacion_id WITH =, daterange(fecha_inicio, fecha_fin, '[)') WITH &&) WHERE (estado IN ('P','C','F'))""")
    print("   aceptada")
except Exception as e:
    print("   ERROR:", str(e).splitlines()[0])
try:
    c.execute("ALTER TABLE reserva_part ADD PRIMARY KEY (reserva_id)")
except Exception as e:
    print(">> PRIMARY KEY (reserva_id) sin la clave de partición -> ERROR:", str(e).splitlines()[0])
c.execute("ALTER TABLE reserva_part ADD PRIMARY KEY (reserva_id, fecha_inicio)")
print(">> PRIMARY KEY (reserva_id, fecha_inicio): aceptada")

t = time.perf_counter()
c.execute("INSERT INTO reserva_part SELECT * FROM reserva")
print(f"carga de {c.execute('SELECT count(*) FROM reserva_part').fetchone()[0]:,} filas: {time.perf_counter()-t:.0f} s")
t = time.perf_counter()
c.execute("CREATE INDEX ON reserva_part (fecha_inicio)")
c.execute("CREATE INDEX ON reserva_part (huesped_id)")
print(f"índices (se crean en cada partición): {time.perf_counter()-t:.0f} s")
c.execute("VACUUM ANALYZE reserva_part")

print("\nTamaño por partición:")
for r in c.execute("""SELECT c.relname, pg_size_pretty(pg_relation_size(c.oid)), pg_size_pretty(pg_indexes_size(c.oid)), c.reltuples::bigint
                        FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
                       WHERE i.inhparent = 'reserva_part'::regclass ORDER BY 1""").fetchall():
    print("   ", r)
print("total particionada:", c.execute("""SELECT pg_size_pretty(sum(pg_total_relation_size(inhrelid))) FROM pg_inherits
                                         WHERE inhparent = 'reserva_part'::regclass""").fetchone()[0],
      "| sin particionar:", c.execute("SELECT pg_size_pretty(pg_total_relation_size('reserva'))").fetchone()[0])

consultas = [
    ("Un mes (filtra por la clave)", "SELECT count(*), sum(tarifa_noche) FROM {t} WHERE fecha_inicio >= '2024-07-01' AND fecha_inicio < '2024-08-01'"),
    ("Un año completo", "SELECT count(*), sum(tarifa_noche) FROM {t} WHERE fecha_inicio >= '2024-01-01' AND fecha_inicio < '2025-01-01'"),
    ("Por huésped (no usa la clave)", "SELECT count(*) FROM {t} WHERE huesped_id = 4242"),
    ("Toda la tabla", "SELECT count(*) FROM {t}"),
    ("Por PK reserva_id (no usa la clave)", "SELECT * FROM {t} WHERE reserva_id = 3333333"),
]
for et, q in consultas:
    for t_ in ("reserva", "reserva_part"):
        ms, n = bench(c, q.format(t=t_), reps=3)
        r = resumen_plan(plan(c, q.format(t=t_)))
        print(f"{et:36} {t_:13} {ms:9.1f} ms | {r['buffers']}")

print("\n>> Mantenimiento: eliminar todo 2015")
c.execute("BEGIN")
t = time.perf_counter(); n = c.execute("DELETE FROM reserva WHERE fecha_inicio < '2016-01-01'").rowcount
print(f"   DELETE en tabla sin particionar: {n:,} filas en {time.perf_counter()-t:.1f} s (deja tuplas muertas; se revierte)")
c.execute("ROLLBACK")
c.execute("BEGIN")
t = time.perf_counter(); c.execute("ALTER TABLE reserva_part DETACH PARTITION reserva_p2015"); c.execute("DROP TABLE reserva_p2015")
print(f"   DETACH + DROP de la partición 2015: {(time.perf_counter()-t)*1000:.0f} ms (se revierte)")
c.execute("ROLLBACK")

# ------------------------------------------------------------------ Punto 51
titulo("PUNTO 51 — Partition pruning")
casos = [
    ("Rango sobre la clave", "SELECT count(*) FROM reserva_part WHERE fecha_inicio >= '2024-07-01' AND fecha_inicio < '2024-08-01'"),
    ("Igualdad sobre la clave", "SELECT count(*) FROM reserva_part WHERE fecha_inicio = '2026-01-15'"),
    ("Función sobre la clave (EXTRACT)", "SELECT count(*) FROM reserva_part WHERE extract(year FROM fecha_inicio) = 2024"),
    ("Filtro sobre otra columna (fecha_fin)", "SELECT count(*) FROM reserva_part WHERE fecha_fin >= '2024-07-01' AND fecha_fin < '2024-08-01'"),
    ("Clave comparada con expresión estable (CURRENT_DATE)", "SELECT count(*) FROM reserva_part WHERE fecha_inicio >= CURRENT_DATE - 30"),
]
for et, q in casos:
    p = plan(c, q)
    parts = sorted(set(re.findall(r"on (reserva_p\w+)", p)))
    removed = re.findall(r"Subplans Removed: (\d+)", p)
    print(f"\n--- {et}\n   particiones visitadas: {len(parts)} {parts[:4]}{'...' if len(parts) > 4 else ''} | subplanes eliminados en ejecución: {removed} | {resumen_plan(p)['ms']} ms")
print("\n--- Plan completo, rango sobre la clave:")
print(plan(c, casos[0][1]))
print("\n--- Sentencia preparada con parámetro (pruning en tiempo de ejecución):")
c.execute("PREPARE q_mes(date, date) AS SELECT count(*) FROM reserva_part WHERE fecha_inicio >= $1 AND fecha_inicio < $2")
c.execute("SET plan_cache_mode = force_generic_plan")
print(plan(c, "EXECUTE q_mes('2024-07-01', '2024-08-01')"))
c.execute("RESET plan_cache_mode")
c.execute("SET enable_partition_pruning = off")
p = plan(c, casos[0][1])
print(f"\n--- Con enable_partition_pruning = off: particiones visitadas {len(set(re.findall(r'on (reserva_p\\w+)', p)))} | {resumen_plan(p)['ms']} ms")
c.execute("RESET enable_partition_pruning")

# ------------------------------------------------------------------ Punto 52
titulo("PUNTO 52 — Vistas y vistas materializadas")
c.execute("""CREATE OR REPLACE VIEW v_reserva_detalle AS
  SELECT r.reserva_id, r.fecha_inicio, r.fecha_fin, r.fecha_fin - r.fecha_inicio AS noches, r.estado,
         r.tarifa_noche, r.tarifa_noche * (r.fecha_fin - r.fecha_inicio) AS importe,
         hb.habitacion_id, hb.numero, th.nombre AS tipo, h.hotel_id, h.nombre AS hotel, h.categoria,
         l.nombre AS localidad, p.nombre AS provincia, hu.huesped_id, hu.apellido, hu.nombre
    FROM reserva r
    JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
    JOIN tipo_habitacion th ON th.tipo_habitacion_id = hb.tipo_habitacion_id
    JOIN hotel h ON h.hotel_id = hb.hotel_id
    JOIN domicilio d ON d.domicilio_id = h.domicilio_id
    JOIN localidad l ON l.localidad_id = d.localidad_id
    JOIN provincia p ON p.provincia_id = l.provincia_id
    JOIN huesped hu ON hu.huesped_id = r.huesped_id""")
print("Vista v_reserva_detalle creada (8 tablas)")
medir(c, "Consulta simple sobre la vista de 8 tablas (PostgreSQL no elimina INNER JOIN innecesarios)",
      "SELECT hotel, apellido, fecha_inicio FROM v_reserva_detalle WHERE reserva_id = 4000000", mostrar_plan=True)

c.execute("DROP MATERIALIZED VIEW IF EXISTS mv_ocupacion_mensual")
t = time.perf_counter()
c.execute("""CREATE MATERIALIZED VIEW mv_ocupacion_mensual AS
  SELECT hb.hotel_id, date_trunc('month', r.fecha_inicio)::date AS mes,
         count(*) AS reservas,
         count(*) FILTER (WHERE r.estado = 'X') AS canceladas,
         sum(r.fecha_fin - r.fecha_inicio) FILTER (WHERE r.estado IN ('C','F')) AS noches,
         sum(r.tarifa_noche * (r.fecha_fin - r.fecha_inicio)) FILTER (WHERE r.estado IN ('C','F')) AS ingresos
    FROM reserva r JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
   GROUP BY 1, 2""")
print(f"CREATE MATERIALIZED VIEW: {time.perf_counter()-t:.1f} s | filas {c.execute('SELECT count(*) FROM mv_ocupacion_mensual').fetchone()[0]:,} | tamaño {tam(c,'mv_ocupacion_mensual')[0]}")
c.execute("CREATE UNIQUE INDEX ON mv_ocupacion_mensual (hotel_id, mes)")
c.execute("ANALYZE mv_ocupacion_mensual")

q_dir = """SELECT h.nombre, sum(r.tarifa_noche * (r.fecha_fin - r.fecha_inicio)) FILTER (WHERE r.estado IN ('C','F')) AS ingresos
             FROM reserva r JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id JOIN hotel h ON h.hotel_id = hb.hotel_id
            WHERE r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01'
            GROUP BY h.nombre ORDER BY ingresos DESC LIMIT 10"""
q_mv = """SELECT h.nombre, sum(m.ingresos) AS ingresos FROM mv_ocupacion_mensual m JOIN hotel h USING (hotel_id)
           WHERE m.mes >= '2025-01-01' AND m.mes < '2026-01-01' GROUP BY h.nombre ORDER BY ingresos DESC LIMIT 10"""
medir(c, "Top 10 hoteles por ingresos 2025 — sobre las tablas", q_dir, reps=3, mostrar_plan=False)
medir(c, "Top 10 hoteles por ingresos 2025 — sobre la vista materializada", q_mv, reps=5, mostrar_plan=True)
iguales = c.execute(q_dir).fetchall() == c.execute(q_mv).fetchall()
print("¿mismo resultado?", iguales)

print("\n>> Desactualización: se confirma una reserva nueva y la vista materializada no la ve")
antes = c.execute("SELECT reservas FROM mv_ocupacion_mensual WHERE hotel_id = 13 AND mes = '2029-03-01'").fetchone()
hab = c.execute("SELECT habitacion_id FROM habitacion WHERE hotel_id = 13 ORDER BY habitacion_id LIMIT 1 OFFSET 5").fetchone()[0]
hotelcol = c.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='reserva' AND column_name='hotel_id'").fetchone()[0]
c.execute(f"""INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin{', hotel_id' if hotelcol else ''})
              SELECT {hab}, 5, '2029-03-01', '2029-03-02'{', 13' if hotelcol else ''}
               WHERE NOT EXISTS (SELECT 1 FROM reserva WHERE habitacion_id = {hab} AND estado IN ('P','C','F')
                                 AND daterange(fecha_inicio, fecha_fin, '[)') && daterange('2029-03-01','2029-03-02','[)'))""")
print("   reservas hotel 13 marzo 2029 en la vista:", antes, "-> sigue igual:", c.execute("SELECT reservas FROM mv_ocupacion_mensual WHERE hotel_id = 13 AND mes = '2029-03-01'").fetchone())
t = time.perf_counter(); c.execute("REFRESH MATERIALIZED VIEW mv_ocupacion_mensual"); a = time.perf_counter() - t
print(f"   REFRESH: {a:.1f} s (bloquea lecturas de la vista mientras corre)")
t = time.perf_counter(); c.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_ocupacion_mensual"); b = time.perf_counter() - t
print(f"   REFRESH CONCURRENTLY: {b:.1f} s (no bloquea lecturas; requiere índice UNIQUE)")
print("   después del REFRESH:", c.execute("SELECT reservas FROM mv_ocupacion_mensual WHERE hotel_id = 13 AND mes = '2029-03-01'").fetchone())

c.execute(f"DELETE FROM reserva WHERE habitacion_id = {hab} AND fecha_inicio = '2029-03-01'")
c.execute("REFRESH MATERIALIZED VIEW mv_ocupacion_mensual")
c.execute("DROP TABLE reserva_part CASCADE")
print("\nFIN")
