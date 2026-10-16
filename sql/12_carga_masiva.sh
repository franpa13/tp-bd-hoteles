#!/bin/bash
# Script 12: carga masiva de reservas generadas por 11_generar_reservas.py
# Uso: ./12_carga_masiva.sh reservas.csv
set -e
CSV="$1"
PSQL="psql -v ON_ERROR_STOP=1"   # toma la conexión de PGHOST, PGPORT, PGUSER, PGPASSWORD y PGDATABASE
COLS="(fecha_creacion, habitacion_id, huesped_id, fecha_inicio, fecha_fin, cantidad_huespedes, estado, tarifa_noche, fecha_confirmacion, observaciones)"

echo "== 1) Comparación de métodos de carga sobre 50.000 filas =="
head -n 50000 "$CSV" > /tmp/muestra.csv
$PSQL -q <<SQL
SET search_path TO hotel;
DROP TABLE IF EXISTS carga_prueba;
CREATE TABLE carga_prueba (LIKE reserva INCLUDING ALL);
SQL
python3 - <<PY
import csv, time, psycopg
rows=[r for r in csv.reader(open('/tmp/muestra.csv'))]
rows=[[x if x!='' else None for x in r] for r in rows]
sql="INSERT INTO hotel.carga_prueba (fecha_creacion, habitacion_id, huesped_id, fecha_inicio, fecha_fin, cantidad_huespedes, estado, tarifa_noche, fecha_confirmacion, observaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
def limpiar(c): c.execute("TRUNCATE hotel.carga_prueba"); c.commit()
import os
c=psycopg.connect(f"host={os.getenv('PGHOST','localhost')} port={os.getenv('PGPORT','5432')} user={os.getenv('PGUSER','postgres')} password={os.getenv('PGPASSWORD','postgres')} dbname={os.getenv('PGDATABASE','hoteles')}")
limpiar(c)
c.autocommit=True; t=time.perf_counter()
for r in rows[:10000]: c.execute(sql, r)
a=time.perf_counter()-t; c.autocommit=False
print(f"INSERT fila por fila, autocommit (10.000 filas): {a:.1f} s -> {10000/a:,.0f} filas/s")
limpiar(c); t=time.perf_counter()
with c.cursor() as cur:
    for r in rows: cur.execute(sql, r)
c.commit(); b=time.perf_counter()-t
print(f"INSERT fila por fila, una transacción (50.000): {b:.1f} s -> {50000/b:,.0f} filas/s")
limpiar(c); t=time.perf_counter()
with c.cursor() as cur: cur.executemany(sql, rows)
c.commit(); d=time.perf_counter()-t
print(f"executemany en lote, una transacción (50.000): {d:.1f} s -> {50000/d:,.0f} filas/s")
limpiar(c); t=time.perf_counter()
with c.cursor() as cur:
    with cur.copy("COPY hotel.carga_prueba (fecha_creacion, habitacion_id, huesped_id, fecha_inicio, fecha_fin, cantidad_huespedes, estado, tarifa_noche, fecha_confirmacion, observaciones) FROM STDIN") as cp:
        for r in rows: cp.write_row(r)
c.commit(); e=time.perf_counter()-t
print(f"COPY (50.000): {e:.1f} s -> {50000/e:,.0f} filas/s")
c.execute("DROP TABLE hotel.carga_prueba"); c.commit()
PY

echo "== 2) Carga principal =="
$PSQL <<SQL
SET search_path TO hotel;
\timing on
-- índice secundario: se crea después de cargar (más rápido que mantenerlo fila a fila)
DROP INDEX IF EXISTS ix_reserva_huesped;
\copy reserva $COLS FROM '$CSV' WITH (FORMAT csv, NULL '')
CREATE INDEX ix_reserva_huesped ON reserva (huesped_id);
VACUUM (ANALYZE) reserva;
SELECT count(*) AS reservas FROM reserva;
SELECT pg_size_pretty(pg_relation_size('reserva')) AS tabla,
       pg_size_pretty(pg_indexes_size('reserva'))  AS indices,
       pg_size_pretty(pg_total_relation_size('reserva')) AS total;
SELECT indexrelid::regclass AS indice, pg_size_pretty(pg_relation_size(indexrelid)) AS tam
  FROM pg_index WHERE indrelid = 'reserva'::regclass;
SELECT pg_size_pretty(pg_database_size('hoteles')) AS base_completa;
SQL
