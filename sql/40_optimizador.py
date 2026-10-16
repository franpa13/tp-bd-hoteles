#!/usr/bin/env python3
"""Script 40: Parte VI — EXPLAIN, SARGabilidad, estadísticas, costos y JOIN (Puntos 29 a 33)."""
import time
from tp import *

c = conectar()

# ---------------------------------------------------------------- Punto 29
titulo("PUNTO 29 — EXPLAIN y EXPLAIN ANALYZE")
q = """SELECT h.nombre, count(*) AS reservas
  FROM reserva r JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
  JOIN hotel h ON h.hotel_id = hb.hotel_id
 WHERE r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01' AND r.estado = 'F'
 GROUP BY h.hotel_id ORDER BY reservas DESC LIMIT 10"""
print("--- EXPLAIN (sólo estimación)\n" + plan(c, q, analyze=False))
print("\n--- EXPLAIN (ANALYZE, BUFFERS)\n" + plan(c, q))
print("\n--- EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS) de una consulta con Sort a disco")
print(plan(c, "SELECT * FROM reserva WHERE fecha_inicio >= '2024-01-01' AND fecha_inicio < '2025-01-01' ORDER BY tarifa_noche DESC LIMIT 100000"))

# ---------------------------------------------------------------- Punto 30
titulo("PUNTO 30 — SARGabilidad")
pares = [
    ("Año con EXTRACT", "SELECT count(*) FROM reserva WHERE extract(year FROM fecha_inicio) = 2024",
     "Año con rango", "SELECT count(*) FROM reserva WHERE fecha_inicio >= '2024-01-01' AND fecha_inicio < '2025-01-01'"),
    ("Aritmética sobre la columna", "SELECT count(*) FROM reserva WHERE fecha_inicio + 30 < DATE '2015-03-01'",
     "Aritmética del lado constante", "SELECT count(*) FROM reserva WHERE fecha_inicio < DATE '2015-03-01' - 30"),
    ("Conversión de tipo en la columna", "SELECT * FROM reserva WHERE huesped_id::text = '4242'",
     "Comparación con el tipo nativo", "SELECT * FROM reserva WHERE huesped_id = 4242"),
    ("Fecha convertida a texto", "SELECT count(*) FROM reserva WHERE fecha_inicio::text LIKE '2024-07%'",
     "Rango de fechas", "SELECT count(*) FROM reserva WHERE fecha_inicio >= '2024-07-01' AND fecha_inicio < '2024-08-01'"),
    ("lower() sin índice funcional", "SELECT huesped_id FROM huesped WHERE lower(apellido) = 'tolaba' AND lower(nombre) = 'rocío'",
     "Igualdad directa", "SELECT huesped_id FROM huesped WHERE apellido = 'Tolaba' AND nombre = 'Rocío'"),
    ("LIKE con comodín inicial", "SELECT count(*) FROM huesped WHERE apellido LIKE '%laba'",
     "LIKE con prefijo", "SELECT count(*) FROM huesped WHERE apellido LIKE 'Tola%'"),
    ("OR entre columnas distintas", "SELECT * FROM reserva WHERE huesped_id = 4242 OR fecha_inicio = '2015-02-03'",
     "UNION de dos búsquedas indexables", "SELECT * FROM reserva WHERE huesped_id = 4242 UNION SELECT * FROM reserva WHERE fecha_inicio = '2015-02-03'"),
    ("COALESCE sobre la columna", "SELECT count(*) FROM reserva WHERE coalesce(fecha_inicio, '1900-01-01') = '2025-02-14'",
     "Columna NOT NULL sin COALESCE", "SELECT count(*) FROM reserva WHERE fecha_inicio = '2025-02-14'"),
]
for e1, q1, e2, q2 in pares:
    medir(c, "NO SARG: " + e1, q1, reps=3, mostrar_plan=False)
    medir(c, "SARG:    " + e2, q2, reps=3, mostrar_plan=False)
print("\nCollation de la base:", c.execute("SELECT datcollate FROM pg_database WHERE datname='hoteles'").fetchone())
c.execute("CREATE INDEX ix_tmp_ape_pattern ON huesped (apellido text_pattern_ops)")
medir(c, "LIKE prefijo con índice text_pattern_ops", "SELECT count(*) FROM huesped WHERE apellido LIKE 'Tola%'", reps=3)
c.execute("DROP INDEX ix_tmp_ape_pattern")

# ---------------------------------------------------------------- Punto 31
titulo("PUNTO 31 — Estadísticas del optimizador")
print("--- Estadísticas de columnas (pg_stats) de reserva")
for r in c.execute("""SELECT attname, null_frac, n_distinct, round(correlation::numeric,3),
                             array_length(histogram_bounds::text::text[],1)
                        FROM pg_stats WHERE tablename='reserva' ORDER BY attname""").fetchall():
    print("  ", r)

print("\n--- Columnas correlacionadas: estado y fecha_confirmacion")
qcor = "SELECT count(*) FROM reserva WHERE estado = 'P' AND fecha_confirmacion IS NULL"
print(plan(c, qcor))
c.execute("CREATE STATISTICS st_estado_conf (mcv) ON estado, (fecha_confirmacion IS NULL) FROM reserva")
c.execute("ANALYZE reserva")
print("\nCon CREATE STATISTICS (mcv) ON estado, (fecha_confirmacion IS NULL):")
print(plan(c, qcor))
c.execute("DROP STATISTICS st_estado_conf")

print("\n--- Estadísticas desactualizadas")
c.execute("DROP TABLE IF EXISTS r_stats")
c.execute("CREATE TABLE r_stats WITH (autovacuum_enabled = off) AS SELECT * FROM reserva WHERE fecha_inicio < '2016-01-01'")
c.execute("CREATE INDEX ON r_stats (fecha_inicio)")
c.execute("ANALYZE r_stats")
n0 = c.execute("SELECT count(*) FROM r_stats").fetchone()[0]
c.execute("""INSERT INTO r_stats SELECT reserva_id, habitacion_id, huesped_id, fecha_inicio + 5479, fecha_fin + 5479,
             cantidad_huespedes, estado, tarifa_noche, fecha_creacion, fecha_confirmacion, observaciones
             FROM reserva WHERE fecha_inicio < '2016-01-01'""")
print(f"filas originales {n0}; se insertó la misma cantidad con fechas de 2030 SIN ANALYZE")
qs = """SELECT h.nombre, count(*) FROM r_stats r JOIN habitacion hb USING (habitacion_id) JOIN hotel h USING (hotel_id)
        WHERE r.fecha_inicio >= '2030-01-01' GROUP BY h.nombre"""
medir(c, "Antes de ANALYZE", qs, reps=3)
c.execute("ANALYZE r_stats")
medir(c, "Después de ANALYZE", qs, reps=3)
c.execute("DROP TABLE r_stats")

print("\n--- default_statistics_target y estimación de n_distinct(huesped_id)")
real = c.execute("SELECT count(DISTINCT huesped_id) FROM reserva").fetchone()[0]
for tgt in (10, 100, 1000):
    c.execute(f"ALTER TABLE reserva ALTER COLUMN huesped_id SET STATISTICS {tgt}")
    t = time.perf_counter(); c.execute("ANALYZE reserva (huesped_id)"); dt_ = time.perf_counter() - t
    nd = c.execute("SELECT n_distinct FROM pg_stats WHERE tablename='reserva' AND attname='huesped_id'").fetchone()[0]
    filas = c.execute("SELECT reltuples FROM pg_class WHERE relname='reserva'").fetchone()[0]
    est = nd if nd > 0 else -nd * filas
    print(f"target {tgt:5}: muestra {300*tgt:7} filas | ANALYZE {dt_*1000:6.0f} ms | n_distinct estimado {est:12,.0f} | real {real:,}")
c.execute("ALTER TABLE reserva ALTER COLUMN huesped_id SET STATISTICS -1")
c.execute("ANALYZE reserva")

# ---------------------------------------------------------------- Punto 32
titulo("PUNTO 32 — Costo y selección del plan: ¿índice o recorrido completo?")
rangos = [("1 día", "2024-07-01", "2024-07-02"), ("1 semana", "2024-07-01", "2024-07-08"),
          ("1 mes", "2024-07-01", "2024-08-01"), ("6 meses", "2024-01-01", "2024-07-01"),
          ("2 años", "2023-01-01", "2025-01-01"), ("6 años", "2019-01-01", "2025-01-01")]
total = c.execute("SELECT count(*) FROM reserva").fetchone()[0]
for rpc in ("4", "1.1"):
    c.execute(f"SET random_page_cost = {rpc}")
    print(f"\n>> random_page_cost = {rpc}")
    for et, a, b in rangos:
        q = f"SELECT sum(tarifa_noche) FROM reserva WHERE fecha_inicio >= '{a}' AND fecha_inicio < '{b}'"
        n = c.execute(f"SELECT count(*) FROM reserva WHERE fecha_inicio >= '{a}' AND fecha_inicio < '{b}'").fetchone()[0]
        elegido = plan(c, q, analyze=False).split("\n")
        nodo = [l.strip() for l in elegido if "Scan" in l][0]
        ms_auto, _ = bench(c, q, reps=3)
        c.execute("SET enable_seqscan = off"); ms_idx, _ = bench(c, q, reps=3)
        costo_idx = plan(c, q, analyze=False).split("\n")[0]
        c.execute("RESET enable_seqscan")
        c.execute("SET enable_indexscan = off; SET enable_bitmapscan = off"); ms_seq, _ = bench(c, q, reps=3)
        costo_seq = plan(c, q, analyze=False).split("\n")[0]
        c.execute("RESET enable_indexscan; RESET enable_bitmapscan")
        print(f"{et:8} sel={100*n/total:6.2f}% | elegido: {nodo[:60]:60} | auto {ms_auto:8.1f} ms | "
              f"índice {ms_idx:8.1f} ms [{costo_idx.split('cost=')[1].split(' ')[0]}] | "
              f"secuencial {ms_seq:8.1f} ms [{costo_seq.split('cost=')[1].split(' ')[0]}]")
c.execute("RESET random_page_cost")

# ---------------------------------------------------------------- Punto 33
titulo("PUNTO 33 — Optimización de JOIN")
qj = """SELECT p.nombre AS provincia, sum(r.tarifa_noche * (r.fecha_fin - r.fecha_inicio)) AS facturado
  FROM reserva r
  JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
  JOIN hotel h       ON h.hotel_id = hb.hotel_id
  JOIN domicilio d   ON d.domicilio_id = h.domicilio_id
  JOIN localidad l   ON l.localidad_id = d.localidad_id
  JOIN provincia p   ON p.provincia_id = l.provincia_id
 WHERE r.estado = 'F' AND r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2025-04-01'
 GROUP BY p.nombre"""
medir(c, "Plan elegido por el optimizador", qj, reps=3)
for metodo, apagar in [("forzando Nested Loop", "SET enable_hashjoin=off; SET enable_mergejoin=off"),
                       ("forzando Merge Join", "SET enable_hashjoin=off; SET enable_nestloop=off")]:
    c.execute(apagar)
    medir(c, metodo, qj, reps=3, mostrar_plan=False)
    c.execute("RESET enable_hashjoin; RESET enable_mergejoin; RESET enable_nestloop")

qj2 = """SELECT p.nombre AS provincia, sum(t.facturado) AS facturado
  FROM (SELECT habitacion_id, sum(tarifa_noche * (fecha_fin - fecha_inicio)) AS facturado
          FROM reserva WHERE estado = 'F' AND fecha_inicio >= '2025-01-01' AND fecha_inicio < '2025-04-01'
         GROUP BY habitacion_id) t
  JOIN habitacion hb ON hb.habitacion_id = t.habitacion_id
  JOIN hotel h       ON h.hotel_id = hb.hotel_id
  JOIN domicilio d   ON d.domicilio_id = h.domicilio_id
  JOIN localidad l   ON l.localidad_id = d.localidad_id
  JOIN provincia p   ON p.provincia_id = l.provincia_id
 GROUP BY p.nombre"""
medir(c, "Reescritura: agregar reservas por habitación ANTES del JOIN", qj2, reps=3)
c.execute("CREATE INDEX ix_tmp_cov_fact ON reserva (fecha_inicio) INCLUDE (estado, habitacion_id, fecha_fin, tarifa_noche)")
c.execute("VACUUM reserva")
medir(c, "Reescritura + índice de cobertura", qj2, reps=3)
print("tamaño índice de cobertura:", tam(c, "ix_tmp_cov_fact")[0])
c.execute("DROP INDEX ix_tmp_cov_fact")
print("\nFIN")
