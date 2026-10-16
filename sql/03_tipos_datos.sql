-- =====================================================================
-- Script 03: evidencia experimental para la selección de tipos de datos
-- =====================================================================
SET search_path TO hotel, public;
\pset pager off

\echo '--- Tamaño en bytes de cada tipo (pg_column_size) ---'
SELECT 'SMALLINT'              AS tipo, pg_column_size(1::smallint)            AS bytes
UNION ALL SELECT 'INTEGER',            pg_column_size(1::int)
UNION ALL SELECT 'BIGINT',             pg_column_size(1::bigint)
UNION ALL SELECT 'BOOLEAN',            pg_column_size(true)
UNION ALL SELECT 'DATE',               pg_column_size(current_date)
UNION ALL SELECT 'TIMESTAMP',          pg_column_size(now()::timestamp)
UNION ALL SELECT 'TIMESTAMPTZ',        pg_column_size(now())
UNION ALL SELECT 'NUMERIC(12,2) 85000.50', pg_column_size(85000.50::numeric(12,2))
UNION ALL SELECT 'REAL',               pg_column_size(85000.50::real)
UNION ALL SELECT 'DOUBLE PRECISION',   pg_column_size(85000.50::float8)
UNION ALL SELECT 'CHAR(10) ''DNI''',   pg_column_size('DNI'::char(10))
UNION ALL SELECT 'VARCHAR(10) ''DNI''',pg_column_size('DNI'::varchar(10))
UNION ALL SELECT 'TEXT ''DNI''',       pg_column_size('DNI'::text);

\echo '--- Precisión: sumar 0.10 un millón de veces ---'
SELECT sum(0.10::numeric)  AS con_numeric,
       sum(0.10::float8)   AS con_double,
       sum(0.10::real)     AS con_real
  FROM generate_series(1, 1000000);

\echo '--- Rango: INTEGER desborda donde BIGINT no ---'
DO $$ BEGIN
  PERFORM 2147483647::int + 1;
EXCEPTION WHEN numeric_value_out_of_range THEN
  RAISE NOTICE 'INTEGER: % ', SQLERRM;
END $$;
SELECT 2147483647::bigint + 1 AS con_bigint;

\echo '--- DATE vs TIMESTAMP: aritmética de noches ---'
SELECT DATE '2027-03-15' - DATE '2027-03-10'                     AS noches_date,
       TIMESTAMP '2027-03-15 10:00' - TIMESTAMP '2027-03-10 14:00' AS diferencia_timestamp;

\echo '--- TIMESTAMPTZ guarda el instante; se muestra en la zona de la sesión ---'
SET TIME ZONE 'America/Argentina/Jujuy';
SELECT TIMESTAMPTZ '2027-03-10 14:00:00-03' AS en_jujuy;
SET TIME ZONE 'Europe/Madrid';
SELECT TIMESTAMPTZ '2027-03-10 14:00:00-03' AS mismo_instante_en_madrid;
RESET TIME ZONE;

\echo '--- CHAR rellena con espacios ---'
SELECT 'DNI'::char(10) || '|' AS char_concat, length('DNI'::char(10)) AS len_char,
       octet_length('DNI'::char(10)) AS bytes_char;

\echo '--- Ancho de fila estimado de reserva (bytes de datos) ---'
SELECT avg(pg_column_size(r.*))::int AS bytes_promedio_fila FROM reserva r;
