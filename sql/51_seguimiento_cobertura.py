#!/usr/bin/env python3
"""Script 51: seguimiento de la optimización 4 (índice de cobertura que el optimizador no eligió)."""
from tp import *

c = conectar()
q4 = ("SELECT fecha_inicio, sum(tarifa_noche * (fecha_fin - fecha_inicio)) FROM reserva "
      "WHERE fecha_inicio >= '2025-01-01' AND fecha_inicio < '2025-07-01' AND estado = 'F' GROUP BY fecha_inicio")
titulo("Optimización 4 — por qué no se usó el índice de cobertura")
print(plan(c, q4, analyze=False))
print("\nvisibilidad de páginas:", c.execute(
    "SELECT relpages, relallvisible, round(100.0*relallvisible/relpages,1) FROM pg_class WHERE relname='reserva'").fetchone())
c.execute("VACUUM (ANALYZE) reserva")
print("tras VACUUM:", c.execute(
    "SELECT relpages, relallvisible, round(100.0*relallvisible/relpages,1) FROM pg_class WHERE relname='reserva'").fetchone())
medir(c, "Plan elegido tras VACUUM", q4, reps=3, mostrar_plan=True)
c.execute("SET enable_indexscan = off; SET enable_bitmapscan = off")
medir(c, "Index Only Scan forzado (enable_indexscan = off)", q4, reps=3, mostrar_plan=True)
c.execute("RESET enable_indexscan; RESET enable_bitmapscan")
print("FIN")
