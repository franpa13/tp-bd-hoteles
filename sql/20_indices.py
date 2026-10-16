#!/usr/bin/env python3
"""Script 20: experimentos de la Parte III (Puntos 12 a 18) sobre la base cargada."""
import time
from tp import *

c = conectar()
c.execute("CREATE EXTENSION IF NOT EXISTS pageinspect")
c.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

# ---------------------------------------------------------------- Punto 12
titulo("PUNTO 12 — B+Tree: altura, páginas y costo de búsqueda")
meta = c.execute("SELECT * FROM bt_metap('reserva_pkey')").fetchone()
print("bt_metap(reserva_pkey):", meta)
nivel = c.execute("SELECT level FROM bt_metap('reserva_pkey')").fetchone()[0]
raiz = c.execute("SELECT root FROM bt_metap('reserva_pkey')").fetchone()[0]
print(f"nivel de la raíz = {nivel} -> altura (niveles) = {nivel + 1}")
print("página raíz:", c.execute("SELECT live_items, avg_item_size, page_size, free_size FROM bt_page_stats('reserva_pkey', %s)", (raiz,)).fetchone())
print("una hoja (página 1):", c.execute("SELECT type, live_items, avg_item_size, free_size FROM bt_page_stats('reserva_pkey', 1)").fetchone())
print("páginas del índice:", c.execute("SELECT pg_relation_size('reserva_pkey')/8192").fetchone()[0],
      "| páginas de la tabla:", c.execute("SELECT pg_relation_size('reserva')/8192").fetchone()[0])

q = "SELECT * FROM reserva WHERE reserva_id = 3000000"
medir(c, "Búsqueda por PK con índice", q)
c.execute("SET enable_indexscan = off; SET enable_bitmapscan = off; SET enable_indexonlyscan = off")
medir(c, "Misma búsqueda forzando recorrido secuencial", q, reps=3)
c.execute("RESET enable_indexscan; RESET enable_bitmapscan; RESET enable_indexonlyscan")

# ---------------------------------------------------------------- Punto 13
titulo("PUNTO 13 — Otros tipos de índices")
# BRIN sobre fecha_creacion (muy correlacionada con el orden físico) vs B-Tree
print("correlación física (pg_stats):")
for r in c.execute("""SELECT attname, round(correlation::numeric,3) FROM pg_stats
                      WHERE tablename='reserva' AND attname IN ('reserva_id','fecha_creacion','fecha_inicio','habitacion_id','huesped_id')
                      ORDER BY 1""").fetchall():
    print("  ", r)
q = ("SELECT count(*), sum(tarifa_noche) FROM reserva "
     "WHERE fecha_creacion >= '2024-03-01' AND fecha_creacion < '2024-03-08'")
c.execute("SET enable_indexscan = off; SET enable_bitmapscan = off")
medir(c, "Rango de una semana por fecha_creacion SIN índice", q, reps=3, mostrar_plan=False)
c.execute("RESET enable_indexscan; RESET enable_bitmapscan")
t = time.perf_counter(); c.execute("CREATE INDEX ix_brin_creacion ON reserva USING brin (fecha_creacion)")
print(f"crear BRIN: {time.perf_counter()-t:.1f} s, tamaño {tam(c,'ix_brin_creacion')[0]}")
medir(c, "Mismo rango con BRIN", q)
c.execute("DROP INDEX ix_brin_creacion")
t = time.perf_counter(); c.execute("CREATE INDEX ix_bt_creacion ON reserva (fecha_creacion)")
print(f"crear B-Tree: {time.perf_counter()-t:.1f} s, tamaño {tam(c,'ix_bt_creacion')[0]}")
medir(c, "Mismo rango con B-Tree", q, mostrar_plan=False)
c.execute("DROP INDEX ix_bt_creacion")
# BRIN sobre una columna NO correlacionada
c.execute("CREATE INDEX ix_brin_hab ON reserva USING brin (habitacion_id)")
medir(c, "BRIN sobre habitacion_id (correlación ~0): habitacion_id = 500",
      "SELECT count(*) FROM reserva WHERE habitacion_id = 500", reps=3)
c.execute("DROP INDEX ix_brin_hab")

# Hash vs B-Tree para igualdad sobre email
c.execute("CREATE INDEX ix_email_hash ON huesped_email USING hash (email)")
c.execute("CREATE INDEX ix_email_btree ON huesped_email (email)")
print("tamaños: hash", tam(c, 'ix_email_hash')[0], "| btree", tam(c, 'ix_email_btree')[0])
qe = "SELECT huesped_id FROM huesped_email WHERE email = 'h777777@trabajo.com.ar'"
c.execute("DROP INDEX ix_email_btree")
medir(c, "Igualdad por email con índice HASH", qe, mostrar_plan=False)
print("rango con HASH:", plan(c, "SELECT count(*) FROM huesped_email WHERE email > 'z'", analyze=False))
c.execute("DROP INDEX ix_email_hash")

# GIN con trigramas para búsquedas '%texto%'
qt = "SELECT count(*) FROM huesped WHERE apellido LIKE '%rrey%'"
medir(c, "LIKE '%rrey%' sin índice", qt, reps=3, mostrar_plan=False)
t = time.perf_counter(); c.execute("CREATE INDEX ix_huesped_trgm ON huesped USING gin (apellido gin_trgm_ops)")
print(f"crear GIN trigramas: {time.perf_counter()-t:.1f} s, tamaño {tam(c,'ix_huesped_trgm')[0]}")
medir(c, "LIKE '%rrey%' con GIN (pg_trgm)", qt)
c.execute("DROP INDEX ix_huesped_trgm")

# Índice parcial: sólo las reservas pendientes
c.execute("CREATE INDEX ix_parcial_pend ON reserva (fecha_inicio) WHERE estado = 'P'")
c.execute("CREATE INDEX ix_total_estado_fecha ON reserva (estado, fecha_inicio)")
print("parcial WHERE estado='P':", tam(c, 'ix_parcial_pend')[0], "| completo (estado, fecha_inicio):", tam(c, 'ix_total_estado_fecha')[0])
c.execute("DROP INDEX ix_total_estado_fecha")
medir(c, "Pendientes que vencen en enero 2027 (índice parcial)",
      "SELECT reserva_id FROM reserva WHERE estado='P' AND fecha_inicio >= '2027-01-01' AND fecha_inicio < '2027-02-01'")
c.execute("DROP INDEX ix_parcial_pend")

# GiST existente: disponibilidad
medir(c, "GiST de la restricción EXCLUDE usado para buscar superposición",
      "SELECT reserva_id FROM reserva WHERE habitacion_id = 1234 "
      "AND daterange(fecha_inicio, fecha_fin, '[)') && daterange('2026-07-10','2026-07-15','[)') "
      "AND estado IN ('P','C','F')")

# ---------------------------------------------------------------- Punto 14
titulo("PUNTO 14 — Índices compuestos y regla del prefijo izquierdo")
c.execute("CREATE INDEX ix_h_ape_nom_nac ON huesped (apellido, nombre, fecha_nacimiento)")
c.execute("ANALYZE huesped")
casos = [
    ("A: apellido",                       "SELECT huesped_id FROM huesped WHERE apellido = 'Tolaba'"),
    ("B: apellido + nombre",              "SELECT huesped_id FROM huesped WHERE apellido = 'Tolaba' AND nombre = 'Rocío'"),
    ("C: apellido + nombre + nacimiento", "SELECT huesped_id FROM huesped WHERE apellido = 'Tolaba' AND nombre = 'Rocío' AND fecha_nacimiento = '1980-05-17'"),
    ("D: apellido + nacimiento (salta nombre)", "SELECT huesped_id FROM huesped WHERE apellido = 'Tolaba' AND fecha_nacimiento = '1980-05-17'"),
    ("E: nombre",                         "SELECT huesped_id FROM huesped WHERE nombre = 'Rocío'"),
    ("F: nombre + nacimiento",            "SELECT huesped_id FROM huesped WHERE nombre = 'Rocío' AND fecha_nacimiento = '1980-05-17'"),
    ("G: nacimiento",                     "SELECT huesped_id FROM huesped WHERE fecha_nacimiento = '1980-05-17'"),
    ("H: ORDER BY apellido, nombre LIMIT 20", "SELECT huesped_id, apellido, nombre FROM huesped ORDER BY apellido, nombre LIMIT 20"),
    ("I: ORDER BY nombre LIMIT 20",       "SELECT huesped_id, apellido, nombre FROM huesped ORDER BY nombre LIMIT 20"),
]
for et, q in casos:
    medir(c, et, q, reps=3)
c.execute("DROP INDEX ix_h_ape_nom_nac")

print("\n### Orden de columnas en reserva: (estado, fecha_inicio) vs (fecha_inicio, estado)")
qs = [("solo estado = 'N'",       "SELECT count(*) FROM reserva WHERE estado = 'N'"),
      ("solo fecha (1 semana)",   "SELECT count(*) FROM reserva WHERE fecha_inicio >= '2025-06-01' AND fecha_inicio < '2025-06-08'"),
      ("estado + fecha (1 mes)",  "SELECT count(*) FROM reserva WHERE estado = 'X' AND fecha_inicio >= '2025-06-01' AND fecha_inicio < '2025-07-01'")]
for nombre, cols in [("ix_est_fecha", "(estado, fecha_inicio)"), ("ix_fecha_est", "(fecha_inicio, estado)")]:
    c.execute(f"CREATE INDEX {nombre} ON reserva {cols}")
    print(f"\n>> índice {cols}  tamaño {tam(c, nombre)[0]}")
    for et, q in qs:
        medir(c, f"{cols} | {et}", q, reps=3)
    c.execute(f"DROP INDEX {nombre}")

# ---------------------------------------------------------------- Punto 15
titulo("PUNTO 15 — Índice de cobertura")
qc = ("SELECT fecha_inicio, sum(tarifa_noche * (fecha_fin - fecha_inicio)) FROM reserva "
      "WHERE fecha_inicio >= '2025-01-01' AND fecha_inicio < '2025-04-01' AND estado = 'F' "
      "GROUP BY fecha_inicio ORDER BY fecha_inicio")
c.execute("CREATE INDEX ix_cov_simple ON reserva (fecha_inicio)")
medir(c, "Con índice simple (fecha_inicio)", qc)
c.execute("DROP INDEX ix_cov_simple")
c.execute("CREATE INDEX ix_cov ON reserva (fecha_inicio) INCLUDE (estado, fecha_fin, tarifa_noche)")
c.execute("VACUUM reserva")
medir(c, "Con índice de cobertura (fecha_inicio) INCLUDE (estado, fecha_fin, tarifa_noche)", qc)
print("tamaño índice cobertura:", tam(c, 'ix_cov')[0])
c.execute("CREATE INDEX ix_cov_simple ON reserva (fecha_inicio)")
print("tamaño índice simple:", tam(c, 'ix_cov_simple')[0])
c.execute("DROP INDEX ix_cov_simple; DROP INDEX ix_cov")

# ---------------------------------------------------------------- Punto 16
titulo("PUNTO 16 — Índices funcionales")
qf = "SELECT huesped_id, nombre, apellido FROM huesped WHERE lower(apellido) = 'mamaní' AND lower(nombre) = 'rocío'"
c.execute("CREATE INDEX ix_ape_nom ON huesped (apellido, nombre)")
medir(c, "lower(...) con índice común (apellido, nombre)", qf, reps=3)
c.execute("CREATE INDEX ix_lower_ape_nom ON huesped (lower(apellido), lower(nombre))")
c.execute("ANALYZE huesped")
medir(c, "lower(...) con índice funcional (lower(apellido), lower(nombre))", qf)
medir(c, "Igualdad sin lower() con el funcional presente (usa el común)",
      "SELECT huesped_id FROM huesped WHERE apellido = 'Mamaní' AND nombre = 'Rocío'", mostrar_plan=True)
c.execute("DROP INDEX ix_ape_nom; DROP INDEX ix_lower_ape_nom")

# ---------------------------------------------------------------- Punto 17
titulo("PUNTO 17 — Cardinalidad y selectividad")
total = c.execute("SELECT reltuples::bigint FROM pg_class WHERE relname='reserva'").fetchone()[0]
print("filas estimadas reserva:", total)
for r in c.execute("""SELECT attname, n_distinct, most_common_vals::text, most_common_freqs::text
                      FROM pg_stats WHERE tablename='reserva'
                      AND attname IN ('estado','cantidad_huespedes','habitacion_id','huesped_id','fecha_inicio','reserva_id','tarifa_noche')
                      ORDER BY attname""").fetchall():
    a, nd, mcv, f = r
    print(f"{a:20} n_distinct={nd}  mcv={(mcv or '')[:70]}  freqs={(f or '')[:60]}")
print("conteos reales por estado:", c.execute("SELECT estado, count(*), round(100.0*count(*)/sum(count(*)) over (),2) FROM reserva GROUP BY 1 ORDER BY 2 DESC").fetchall())
c.execute("CREATE INDEX ix_estado ON reserva (estado)")
c.execute("ANALYZE reserva")
for e in ['N', 'P', 'F']:
    medir(c, f"estado = '{e}'", f"SELECT reserva_id FROM reserva WHERE estado = '{e}'", reps=3, mostrar_plan=True)
print("tamaño índice estado:", tam(c, 'ix_estado')[0])
c.execute("DROP INDEX ix_estado")

# ---------------------------------------------------------------- Punto 18
titulo("PUNTO 18 — ¿Por qué no indexar todo?")
c.execute("DROP TABLE IF EXISTS r_pocos, r_muchos")
for t_ in ("r_pocos", "r_muchos"):
    c.execute(f"CREATE TABLE {t_} AS SELECT * FROM reserva WHERE reserva_id <= 1000000")
    c.execute(f"ALTER TABLE {t_} ADD PRIMARY KEY (reserva_id)")
c.execute("CREATE INDEX ON r_pocos (huesped_id)")
c.execute("CREATE INDEX ON r_pocos (fecha_inicio)")
for col in ["huesped_id", "fecha_inicio", "habitacion_id", "fecha_fin", "estado", "tarifa_noche",
            "fecha_creacion", "fecha_confirmacion", "cantidad_huespedes", "observaciones"]:
    c.execute(f"CREATE INDEX ON r_muchos ({col})")
c.execute("CREATE INDEX ON r_muchos (habitacion_id, fecha_inicio)")
c.execute("CREATE INDEX ON r_muchos (estado, fecha_inicio)")
c.execute("VACUUM ANALYZE r_pocos"); c.execute("VACUUM ANALYZE r_muchos")
for t_ in ("r_pocos", "r_muchos"):
    n_idx = c.execute("SELECT count(*) FROM pg_index WHERE indrelid=%s::regclass", (t_,)).fetchone()[0]
    print(f"{t_}: {n_idx} índices | tabla {tam(c,t_)[0]} | índices "
          + c.execute("SELECT pg_size_pretty(pg_indexes_size(%s::regclass))", (t_,)).fetchone()[0])

ops = [
    ("INSERT 100.000", "INSERT INTO {t} SELECT reserva_id + 10000000, habitacion_id, huesped_id, fecha_inicio, fecha_fin, cantidad_huespedes, estado, tarifa_noche, fecha_creacion, fecha_confirmacion, observaciones FROM {t} WHERE reserva_id <= 100000"),
    ("UPDATE 100.000 (columna indexada en r_muchos)", "UPDATE {t} SET tarifa_noche = tarifa_noche + 1 WHERE reserva_id BETWEEN 200001 AND 300000"),
    ("UPDATE 100.000 (columna no indexada en ninguna)", "UPDATE {t} SET cantidad_huespedes = cantidad_huespedes WHERE reserva_id BETWEEN 300001 AND 400000"),
    ("DELETE 100.000", "DELETE FROM {t} WHERE reserva_id > 10000000"),
]
for et, sql in ops:
    for t_ in ("r_pocos", "r_muchos"):
        c.execute("CHECKPOINT")
        t = time.perf_counter(); c.execute(sql.format(t=t_)); dt_ = time.perf_counter() - t
        print(f"{et:52} {t_:9} {dt_*1000:9.0f} ms")
c.execute("VACUUM ANALYZE r_pocos"); c.execute("VACUUM ANALYZE r_muchos")
lecturas = [("reservas de un huésped", "SELECT * FROM {t} WHERE huesped_id = 4242"),
            ("reservas de una habitación en 2015", "SELECT * FROM {t} WHERE habitacion_id = 77 AND fecha_inicio >= '2015-01-01' AND fecha_inicio < '2016-01-01'"),
            ("canceladas de un día", "SELECT * FROM {t} WHERE estado = 'X' AND fecha_inicio = '2015-08-10'")]
for et, sql in lecturas:
    for t_ in ("r_pocos", "r_muchos"):
        ms, n = bench(c, sql.format(t=t_), reps=5)
        print(f"LECTURA {et:40} {t_:9} {ms:8.2f} ms  filas={n}")
print("Índices de r_muchos nunca usados por las lecturas (idx_scan = 0):")
for r in c.execute("SELECT indexrelname, idx_scan, pg_size_pretty(pg_relation_size(indexrelid)) FROM pg_stat_user_indexes WHERE relname='r_muchos' ORDER BY idx_scan, indexrelname").fetchall():
    print("  ", r)
c.execute("DROP TABLE r_pocos, r_muchos")
print("\nFIN")
