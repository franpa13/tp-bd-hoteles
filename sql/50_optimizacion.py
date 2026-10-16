#!/usr/bin/env python3
"""Script 50: Parte VII — 8 consultas optimizadas con el ciclo medir → analizar → hipótesis → cambio → medir."""
import time
from tp import *

c = conectar()
RESUMEN = []


def costo_insert(etiqueta):
    """Costo de insertar 20.000 reservas (luego se revierte), para medir efectos secundarios."""
    con_hotel = c.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='reserva' AND column_name='hotel_id'").fetchone()[0]
    col, val = (", hotel_id", ", hotel_id") if con_hotel else ("", "")
    c.execute("BEGIN")
    t = time.perf_counter()
    c.execute(f"""INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin, cantidad_huespedes, estado{col})
                 SELECT habitacion_id, 1 + g % 900000, DATE '2028-01-01' + (g / 7663) * 3, DATE '2028-01-03' + (g / 7663) * 3, 1, 'P'{val}
                   FROM generate_series(0, 19999) g JOIN habitacion ON habitacion_id = 1 + g % 7663""")
    dt_ = (time.perf_counter() - t) * 1000
    c.execute("ROLLBACK")
    print(f"[costo INSERT 20.000 reservas — {etiqueta}] {dt_:.0f} ms")
    return dt_


def caso(n, nombre, original, optimizada, preparar=None, deshacer=None, reps=5):
    titulo(f"OPTIMIZACIÓN {n} — {nombre}")
    ms0, r0 = medir(c, "ORIGINAL", original, reps=reps)
    extra = ""
    if preparar:
        t = time.perf_counter()
        for s in preparar:
            c.execute(s)
        extra = f"cambio aplicado en {time.perf_counter()-t:.1f} s"
        print(extra)
    ms1, r1 = medir(c, "OPTIMIZADA", optimizada, reps=reps)
    RESUMEN.append((n, nombre, ms0, ms1, r0["buffers"], r1["buffers"]))
    print(f">> {ms0:.1f} ms -> {ms1:.1f} ms  (x{ms0/ms1:.1f})")


base_insert = costo_insert("índices de la estrategia base")

# 1. SARGabilidad
caso(1, "Reservas por año: EXTRACT → rango",
     "SELECT count(*), sum(tarifa_noche) FROM reserva WHERE extract(year FROM fecha_inicio) = 2024 AND extract(month FROM fecha_inicio) = 7",
     "SELECT count(*), sum(tarifa_noche) FROM reserva WHERE fecha_inicio >= '2024-07-01' AND fecha_inicio < '2024-08-01'")

# 2. Historial del huésped: índice compuesto que elimina el Sort
caso(2, "Últimas 10 reservas de un huésped frecuente: índice (huesped_id, fecha_inicio DESC)",
     "SELECT reserva_id, fecha_inicio, fecha_fin, estado FROM reserva WHERE huesped_id = 1 ORDER BY fecha_inicio DESC LIMIT 10",
     "SELECT reserva_id, fecha_inicio, fecha_fin, estado FROM reserva WHERE huesped_id = 1 ORDER BY fecha_inicio DESC LIMIT 10",
     preparar=["CREATE INDEX ix_reserva_huesped_fecha ON reserva (huesped_id, fecha_inicio DESC)", "ANALYZE reserva"])
print("tamaño nuevo índice:", tam(c, "ix_reserva_huesped_fecha")[0], "| reemplaza a ix_reserva_huesped:", tam(c, "ix_reserva_huesped")[0])
c.execute("DROP INDEX ix_reserva_huesped")   # el compuesto también sirve a la FK (prefijo izquierdo)

# 3. Búsqueda sin distinguir mayúsculas
caso(3, "Búsqueda de huésped sin distinguir mayúsculas: índice funcional",
     "SELECT huesped_id, apellido, nombre FROM huesped WHERE lower(apellido) = 'choque' AND lower(nombre) = 'micaela'",
     "SELECT huesped_id, apellido, nombre FROM huesped WHERE lower(apellido) = 'choque' AND lower(nombre) = 'micaela'",
     preparar=["CREATE INDEX ix_huesped_lower ON huesped (lower(apellido), lower(nombre))", "ANALYZE huesped"])

# 4. Facturación por día: índice de cobertura
q4 = ("SELECT fecha_inicio, sum(tarifa_noche * (fecha_fin - fecha_inicio)) FROM reserva "
      "WHERE fecha_inicio >= '2025-01-01' AND fecha_inicio < '2025-07-01' AND estado = 'F' GROUP BY fecha_inicio")
caso(4, "Facturación diaria de un semestre: índice de cobertura", q4, q4,
     preparar=["CREATE INDEX ix_reserva_fact_cov ON reserva (fecha_inicio) INCLUDE (estado, fecha_fin, tarifa_noche)", "VACUUM ANALYZE reserva"])

# 5. Ranking de hoteles: desnormalización controlada (script 05)
q5o = """SELECT hb.hotel_id, count(*) FROM reserva r JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
          WHERE r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2025-02-01' AND hb.hotel_id = 13 GROUP BY hb.hotel_id"""
q5n = """SELECT hotel_id, count(*) FROM reserva
          WHERE hotel_id = 13 AND fecha_inicio >= '2025-01-01' AND fecha_inicio < '2025-02-01' GROUP BY hotel_id"""
caso(5, "Reservas de un hotel en un mes: hotel_id en reserva + índice (hotel_id, fecha_inicio)", q5o, q5n,
     preparar=[open("05_desnormalizacion.sql", encoding="utf-8").read().replace("SET search_path TO hotel, public;", "")])
print("tamaño ix_reserva_hotel_fecha:", tam(c, "ix_reserva_hotel_fecha")[0],
      "| tabla reserva ahora:", tam(c, "reserva")[0])

# 6. Paginación
caso(6, "Paginación profunda: OFFSET → keyset (seek)",
     "SELECT reserva_id, fecha_inicio, huesped_id FROM reserva ORDER BY reserva_id LIMIT 50 OFFSET 5000000",
     "SELECT reserva_id, fecha_inicio, huesped_id FROM reserva WHERE reserva_id > 5000000 ORDER BY reserva_id LIMIT 50")

# 7. NOT IN → NOT EXISTS
c.execute("SET statement_timeout = '120s'")
caso(7, "Huéspedes sin reservas desde 2025: NOT IN → NOT EXISTS",
     "SELECT count(*) FROM huesped WHERE huesped_id NOT IN (SELECT huesped_id FROM reserva WHERE fecha_inicio >= '2025-01-01')",
     "SELECT count(*) FROM huesped h WHERE NOT EXISTS (SELECT 1 FROM reserva r WHERE r.huesped_id = h.huesped_id AND r.fecha_inicio >= '2025-01-01')",
     reps=2)
c.execute("RESET statement_timeout")

# 8. Subconsulta correlacionada en SELECT → JOIN + GROUP BY
caso(8, "Reservas 2025 por hotel: subconsulta correlacionada → JOIN agregado",
     """SELECT h.nombre, (SELECT count(*) FROM reserva r JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
                           WHERE hb.hotel_id = h.hotel_id AND r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01') AS reservas
          FROM hotel h ORDER BY reservas DESC LIMIT 10""",
     """SELECT h.nombre, count(*) AS reservas FROM reserva r JOIN hotel h ON h.hotel_id = r.hotel_id
         WHERE r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01'
         GROUP BY h.hotel_id ORDER BY reservas DESC LIMIT 10""", reps=3)

# ------------------------------------------------ Punto 37: efectos secundarios
titulo("PUNTO 37 — Validación y efectos secundarios")
nuevo_insert = costo_insert("con los índices agregados por la optimización")
print(f"INSERT: {base_insert:.0f} ms -> {nuevo_insert:.0f} ms")
for r in c.execute("""SELECT indexrelid::regclass, pg_size_pretty(pg_relation_size(indexrelid))
                        FROM pg_index WHERE indrelid = 'reserva'::regclass ORDER BY pg_relation_size(indexrelid) DESC""").fetchall():
    print("  ", r)
print("total índices reserva:", c.execute("SELECT pg_size_pretty(pg_indexes_size('reserva'))").fetchone()[0])
# ¿empeoró alguna consulta? la historia por huésped ahora usa el compuesto; probamos la consulta de FK
medir(c, "Consulta por FK huesped_id (ahora resuelta por el índice compuesto)",
      "SELECT count(*) FROM reserva WHERE huesped_id = 777", mostrar_plan=True)
c.execute("ANALYZE")

titulo("RESUMEN")
for n, nom, a, b, ba, bb in RESUMEN:
    print(f"{n}. {nom[:70]:70} {a:10.1f} ms -> {b:9.1f} ms  x{a/b:7.1f} | {ba} -> {bb}")
print("\nFIN")
