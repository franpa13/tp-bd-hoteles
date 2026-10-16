#!/usr/bin/env python3
"""Script 81: complemento del Punto 50/51 — consultas que el índice de cobertura no resuelve y pruning desactivado."""
import re
from tp import *

c = conectar()
c.execute("DROP TABLE IF EXISTS reserva_part CASCADE")
c.execute("CREATE TABLE reserva_part (LIKE reserva INCLUDING DEFAULTS) PARTITION BY RANGE (fecha_inicio)")
for y in range(2015, 2028):
    c.execute(f"CREATE TABLE reserva_p{y} PARTITION OF reserva_part FOR VALUES FROM ('{y}-01-01') TO ('{y+1}-01-01')")
c.execute("CREATE TABLE reserva_pdef PARTITION OF reserva_part DEFAULT")
c.execute("ALTER TABLE reserva_part ADD PRIMARY KEY (reserva_id, fecha_inicio)")
c.execute("INSERT INTO reserva_part SELECT * FROM reserva")
c.execute("CREATE INDEX ON reserva_part (fecha_inicio)")
c.execute("CREATE INDEX ON reserva_part (huesped_id)")
c.execute("VACUUM ANALYZE reserva_part")

titulo("PUNTO 50b — Columnas que no están en ningún índice (cantidad_huespedes, observaciones)")
consultas = [
    ("Un mes", "SELECT avg(cantidad_huespedes), count(observaciones) FROM {t} WHERE fecha_inicio >= '2024-07-01' AND fecha_inicio < '2024-08-01'"),
    ("Un trimestre", "SELECT avg(cantidad_huespedes), count(observaciones) FROM {t} WHERE fecha_inicio >= '2024-01-01' AND fecha_inicio < '2024-04-01'"),
    ("Un año", "SELECT avg(cantidad_huespedes), count(observaciones) FROM {t} WHERE fecha_inicio >= '2024-01-01' AND fecha_inicio < '2025-01-01'"),
    ("Dos años", "SELECT avg(cantidad_huespedes), count(observaciones) FROM {t} WHERE fecha_inicio >= '2023-01-01' AND fecha_inicio < '2025-01-01'"),
]
for et, q in consultas:
    for t_ in ("reserva", "reserva_part"):
        ms, n = bench(c, q.format(t=t_), reps=3)
        r = resumen_plan(plan(c, q.format(t=t_)))
        print(f"{et:14} {t_:13} {ms:8.1f} ms | {r['buffers']} | {r['nodos'][:2]}")

titulo("PUNTO 51b — enable_partition_pruning = off")
q = "SELECT count(*) FROM reserva_part WHERE fecha_inicio >= '2024-07-01' AND fecha_inicio < '2024-08-01'"
for valor in ("on", "off"):
    c.execute(f"SET enable_partition_pruning = {valor}")
    p = plan(c, q)
    parts = sorted(set(re.findall(r"on (reserva_p\w+)", p)))
    print(f"enable_partition_pruning = {valor}: particiones visitadas {len(parts)} | {resumen_plan(p)['ms']} ms | {resumen_plan(p)['buffers']}")
c.execute("RESET enable_partition_pruning")
c.execute("DROP TABLE reserva_part CASCADE")
print("FIN")
