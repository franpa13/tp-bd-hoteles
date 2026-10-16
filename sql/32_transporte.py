#!/usr/bin/env python3
"""Script 32: Punto 28 — transporte de datos: pocas/muchas filas, pocas/muchas columnas, LIMIT y paginación."""
import time
from tp import *

c = conectar()
filtro = "fecha_inicio >= '2024-01-01' AND fecha_inicio < '2025-01-01'"


def transporte(etiqueta, sql):
    srv = resumen_plan(plan(c, sql))["ms"]
    ts = []
    for _ in range(3):
        t = time.perf_counter(); cur = c.execute(sql); filas = cur.fetchall(); ts.append((time.perf_counter() - t) * 1000)
    ts.sort(); cli = ts[1]
    # bytes en formato texto que viajan por el protocolo (aprox.: suma de longitudes de cada valor)
    muestra = filas[:20000]
    bytes_ = sum(len(str(v)) for f in muestra for v in f if v is not None) * len(filas) / max(1, len(muestra))
    print(f"{etiqueta:58} filas {len(filas):9,} | servidor {srv:8.1f} ms | cliente {cli:8.1f} ms | ~{bytes_/1e6:7.2f} MB")
    return cli


titulo("PUNTO 28 — Pocas/muchas filas y pocas/muchas columnas")
transporte("1 fila, 2 columnas (por PK)", "SELECT reserva_id, fecha_inicio FROM reserva WHERE reserva_id = 4242424")
transporte("1 fila, SELECT * con JOIN a 4 tablas (muchas columnas)",
           "SELECT * FROM reserva r JOIN habitacion hb USING (habitacion_id) JOIN hotel h ON h.hotel_id = hb.hotel_id "
           "JOIN huesped hu USING (huesped_id) WHERE r.reserva_id = 4242424")
transporte("Agregado de un año en el servidor (1 fila)", f"SELECT count(*), sum(tarifa_noche) FROM reserva WHERE {filtro}")
transporte("Un año, 2 columnas", f"SELECT reserva_id, tarifa_noche FROM reserva WHERE {filtro}")
transporte("Un año, SELECT * (11 columnas)", f"SELECT * FROM reserva WHERE {filtro}")
transporte("Un año, SELECT * con JOIN a 4 tablas (~40 columnas)",
           f"SELECT * FROM reserva r JOIN habitacion hb USING (habitacion_id) JOIN hotel h ON h.hotel_id = hb.hotel_id "
           f"JOIN huesped hu USING (huesped_id) WHERE r.{filtro.replace(' AND ', ' AND r.')}")

titulo("SELECT * vs columnas necesarias con índice de cobertura")
c.execute("CREATE INDEX ix_tmp_hue_fecha ON reserva (huesped_id, fecha_inicio) INCLUDE (estado)")
c.execute("VACUUM reserva")
medir(c, "Columnas necesarias (Index Only Scan posible)",
      "SELECT fecha_inicio, estado FROM reserva WHERE huesped_id BETWEEN 1 AND 50", reps=5, mostrar_plan=False)
medir(c, "SELECT * (obliga a ir a la tabla)",
      "SELECT * FROM reserva WHERE huesped_id BETWEEN 1 AND 50", reps=5, mostrar_plan=False)
c.execute("DROP INDEX ix_tmp_hue_fecha")

titulo("LIMIT")
medir(c, "ORDER BY fecha_inicio DESC LIMIT 20 (índice entrega el orden)",
      "SELECT * FROM reserva ORDER BY fecha_inicio DESC LIMIT 20", mostrar_plan=False)
medir(c, "ORDER BY tarifa_noche DESC LIMIT 20 (sin índice: top-N heapsort)",
      "SELECT * FROM reserva ORDER BY tarifa_noche DESC NULLS LAST LIMIT 20", reps=3, mostrar_plan=True)
medir(c, "Sin LIMIT y cortando en el cliente (trae todo el año)",
      f"SELECT * FROM reserva WHERE {filtro} ORDER BY fecha_inicio", reps=3, mostrar_plan=False)

titulo("Paginación: OFFSET vs keyset, páginas de 50 filas ordenadas por reserva_id")
for pagina in (1, 100, 10000, 100000, 150000):
    off = (pagina - 1) * 50
    ms_off, _ = bench(c, f"SELECT reserva_id, fecha_inicio, huesped_id FROM reserva ORDER BY reserva_id LIMIT 50 OFFSET {off}", reps=3)
    ultimo = c.execute(f"SELECT reserva_id FROM reserva ORDER BY reserva_id LIMIT 1 OFFSET {max(off-1,0)}").fetchone()[0] if off else 0
    ms_key, _ = bench(c, f"SELECT reserva_id, fecha_inicio, huesped_id FROM reserva WHERE reserva_id > {ultimo} ORDER BY reserva_id LIMIT 50", reps=3)
    p_off = resumen_plan(plan(c, f"SELECT reserva_id, fecha_inicio, huesped_id FROM reserva ORDER BY reserva_id LIMIT 50 OFFSET {off}"))
    p_key = resumen_plan(plan(c, f"SELECT reserva_id, fecha_inicio, huesped_id FROM reserva WHERE reserva_id > {ultimo} ORDER BY reserva_id LIMIT 50"))
    print(f"página {pagina:7,} (OFFSET {off:9,}): OFFSET {ms_off:9.2f} ms [{p_off['buffers']}] | keyset {ms_key:6.2f} ms [{p_key['buffers']}]")
print("\nKeyset con orden compuesto (fecha_inicio, reserva_id):")
medir(c, "página siguiente después de (2024-07-01, 4000000)",
      "SELECT reserva_id, fecha_inicio FROM reserva WHERE (fecha_inicio, reserva_id) > ('2024-07-01', 4000000) "
      "ORDER BY fecha_inicio, reserva_id LIMIT 50", mostrar_plan=True)
print("\nFIN")
