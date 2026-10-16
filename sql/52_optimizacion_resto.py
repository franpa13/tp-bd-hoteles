#!/usr/bin/env python3
"""
Script 52: continuación de 50_optimizacion.py (optimizaciones 7 y 8 y Punto 37).
La optimización 7 original (NOT IN) superó el statement_timeout de 120 s en 50_optimizacion.py;
aquí se mide una sola vez con un límite de 5 minutos.
"""
import time
from tp import *

c = conectar()

titulo("OPTIMIZACIÓN 7 — Huéspedes sin reservas desde 2025: NOT IN → NOT EXISTS")
q_in = "SELECT count(*) FROM huesped WHERE huesped_id NOT IN (SELECT huesped_id FROM reserva WHERE fecha_inicio >= '2025-01-01')"
q_ex = ("SELECT count(*) FROM huesped h WHERE NOT EXISTS "
        "(SELECT 1 FROM reserva r WHERE r.huesped_id = h.huesped_id AND r.fecha_inicio >= '2025-01-01')")
print("--- ORIGINAL: plan estimado (sin ejecutar)\n" + plan(c, q_in, analyze=False))
c.execute("SET statement_timeout = '5min'")
t = time.perf_counter()
try:
    n = c.execute(q_in).fetchone()[0]
    ms0 = (time.perf_counter() - t) * 1000
    print(f"ORIGINAL ejecutada una vez: {ms0/1000:.1f} s, resultado {n}")
except Exception as e:
    ms0 = (time.perf_counter() - t) * 1000
    print(f"ORIGINAL cancelada tras {ms0/1000:.0f} s: {str(e).splitlines()[0]}")
c.execute("RESET statement_timeout")
c.execute("SET work_mem = '64MB'")
print("--- ORIGINAL con work_mem = 64MB (la subconsulta entra en memoria como hashed SubPlan)")
ms_wm, r_wm = medir(c, "NOT IN con work_mem 64MB", q_in, reps=2)
c.execute("RESET work_mem")
ms1, r1 = medir(c, "OPTIMIZADA (NOT EXISTS → Hash Anti Join)", q_ex, reps=3)
print(f">> {ms0:.1f} ms -> {ms1:.1f} ms  (x{ms0/ms1:.1f})")

titulo("OPTIMIZACIÓN 8 — Reservas 2025 por hotel: subconsulta correlacionada → JOIN agregado")
q8o = """SELECT h.nombre, (SELECT count(*) FROM reserva r JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
                           WHERE hb.hotel_id = h.hotel_id AND r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01') AS reservas
          FROM hotel h ORDER BY reservas DESC LIMIT 10"""
q8n = """SELECT h.nombre, count(*) AS reservas FROM reserva r JOIN hotel h ON h.hotel_id = r.hotel_id
         WHERE r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01'
         GROUP BY h.hotel_id ORDER BY reservas DESC LIMIT 10"""
ms0, r0 = medir(c, "ORIGINAL", q8o, reps=3)
ms1, r1 = medir(c, "OPTIMIZADA", q8n, reps=3)
print(f">> {ms0:.1f} ms -> {ms1:.1f} ms  (x{ms0/ms1:.1f})")
print("¿mismo resultado?", c.execute(q8o).fetchall() == c.execute(q8n).fetchall())

titulo("PUNTO 37 — Validación y efectos secundarios")
c.execute("BEGIN")
t = time.perf_counter()
c.execute("""INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin, cantidad_huespedes, estado, hotel_id)
             SELECT habitacion_id, 1 + g % 900000, DATE '2028-01-01' + (g / 7663) * 3, DATE '2028-01-03' + (g / 7663) * 3, 1, 'P', hotel_id
               FROM generate_series(0, 19999) g JOIN habitacion ON habitacion_id = 1 + g % 7663""")
dt_ = (time.perf_counter() - t) * 1000
c.execute("ROLLBACK")
print(f"[costo INSERT 20.000 reservas — con los índices agregados por la optimización] {dt_:.0f} ms")
for r in c.execute("""SELECT indexrelid::regclass, pg_size_pretty(pg_relation_size(indexrelid))
                        FROM pg_index WHERE indrelid = 'reserva'::regclass ORDER BY pg_relation_size(indexrelid) DESC""").fetchall():
    print("  ", r)
print("tabla reserva:", tam(c, "reserva")[0], "| total índices:", c.execute("SELECT pg_size_pretty(pg_indexes_size('reserva'))").fetchone()[0])
print("tuplas muertas tras el UPDATE de hotel_id:", c.execute("SELECT n_live_tup, n_dead_tup FROM pg_stat_user_tables WHERE relname='reserva'").fetchone())
medir(c, "Consulta por FK huesped_id (ahora resuelta por el índice compuesto)",
      "SELECT count(*) FROM reserva WHERE huesped_id = 777", mostrar_plan=True)
medir(c, "Consulta por año que antes usaba ix_reserva_fecha_inicio (¿cambió el plan?)",
      "SELECT count(*), sum(tarifa_noche) FROM reserva WHERE fecha_inicio >= '2024-07-01' AND fecha_inicio < '2024-08-01'", mostrar_plan=True)
print("\nFIN")
