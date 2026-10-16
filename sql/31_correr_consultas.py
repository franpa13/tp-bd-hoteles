#!/usr/bin/env python3
"""Script 31: ejecuta y mide cada consulta de 30_consultas.sql (Punto 22: 1 calentamiento + 3 repeticiones)."""
import re, sys
from tp import *

texto = open("30_consultas.sql", encoding="utf-8").read()
bloques = re.split(r"^-- @", texto, flags=re.M)[1:]
c = conectar()
filtro = sys.argv[1] if len(sys.argv) > 1 else ""
for b in bloques:
    cab, sql = b.split("\n", 1)
    qid, titulo_q = cab.split(" ", 1)
    if not qid.startswith(filtro):
        continue
    sql = re.sub(r"^-- =+.*$", "", sql, flags=re.M).strip().rstrip(";")
    sql = sql.split(";\n")[0]
    ms, n = bench(c, sql, reps=3)
    p = plan(c, sql)
    r = resumen_plan(p)
    tablas = len(set(re.findall(r"\b(?:FROM|JOIN)\s+(\w+)", sql)))
    filas = c.execute(sql).fetchmany(3)
    print(f"\n### {qid} {titulo_q}\n tablas={tablas} | mediana {ms:.1f} ms | filas {n} | {r['buffers']}\n nodos: {r['nodos']}\n muestra: {filas}")
