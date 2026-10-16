-- =====================================================================
-- Script 04: impacto de las restricciones físicas en la escritura.
-- Inserta las mismas 500.000 reservas no superpuestas en tres copias de
-- la tabla: sin restricciones, con PK+FK+CHECK, y completa (+EXCLUDE).
-- =====================================================================
SET search_path TO hotel, public;
\timing on
\pset pager off

-- Datos auxiliares: 1.000 habitaciones de un hotel, 1 huésped
INSERT INTO habitacion (hotel_id, tipo_habitacion_id, numero, piso)
SELECT 1, 1, 'X' || g, 1 FROM generate_series(1, 1000) g;

-- 500.000 reservas: 500 por habitación, consecutivas de 3 noches
CREATE TEMP TABLE fuente AS
SELECT h.habitacion_id, 1::bigint AS huesped_id,
       DATE '2020-01-01' + (k * 3)     AS fecha_inicio,
       DATE '2020-01-01' + (k * 3 + 3) AS fecha_fin
  FROM habitacion h CROSS JOIN generate_series(0, 499) k
 WHERE h.numero LIKE 'X%';

CREATE TABLE r_sin (LIKE reserva INCLUDING DEFAULTS);
ALTER TABLE r_sin ALTER COLUMN reserva_id ADD GENERATED ALWAYS AS IDENTITY;
CREATE TABLE r_basica (LIKE reserva INCLUDING DEFAULTS INCLUDING CONSTRAINTS);
ALTER TABLE r_basica ALTER COLUMN reserva_id ADD GENERATED ALWAYS AS IDENTITY,
  ADD PRIMARY KEY (reserva_id),
  ADD FOREIGN KEY (habitacion_id) REFERENCES habitacion,
  ADD FOREIGN KEY (huesped_id) REFERENCES huesped;

\echo '--- A) sin restricciones ---'
INSERT INTO r_sin (habitacion_id, huesped_id, fecha_inicio, fecha_fin) SELECT * FROM fuente;
\echo '--- B) PK + FK + CHECK ---'
INSERT INTO r_basica (habitacion_id, huesped_id, fecha_inicio, fecha_fin) SELECT * FROM fuente;
\echo '--- C) completa: PK + FK + CHECK + EXCLUDE (GiST) + trigger ---'
INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin) SELECT * FROM fuente;

\echo '--- Tamaños resultantes ---'
SELECT c.relname AS tabla,
       pg_size_pretty(pg_relation_size(c.oid))       AS datos,
       pg_size_pretty(pg_indexes_size(c.oid))        AS indices,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total
  FROM pg_class c
 WHERE c.relname IN ('r_sin','r_basica','reserva') AND c.relnamespace = 'hotel'::regnamespace;

\echo '--- D) completa sin trigger (aísla el costo del EXCLUDE) ---'
DELETE FROM reserva WHERE habitacion_id IN (SELECT habitacion_id FROM habitacion WHERE numero LIKE 'X%');
ALTER TABLE reserva DISABLE TRIGGER trg_reserva_capacidad;
INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin) SELECT * FROM fuente;
ALTER TABLE reserva ENABLE TRIGGER trg_reserva_capacidad;

DROP TABLE r_sin, r_basica;
