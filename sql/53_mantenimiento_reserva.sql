-- =====================================================================
-- Script 53: mantenimiento de reserva después de la Parte VII (Punto 48)
-- El UPDATE masivo de hotel_id (desnormalización) duplicó tabla e índices.
-- =====================================================================
SET search_path TO hotel, public;
\pset pager off
\timing on
\echo '--- Antes'
SELECT pg_size_pretty(pg_relation_size('reserva')) AS tabla, pg_size_pretty(pg_indexes_size('reserva')) AS indices;
SELECT indexrelid::regclass AS indice, pg_size_pretty(pg_relation_size(indexrelid)) AS tam
  FROM pg_index WHERE indrelid = 'reserva'::regclass ORDER BY pg_relation_size(indexrelid) DESC;
\echo '--- VACUUM FULL (reescribe la tabla y reconstruye todos los índices; bloqueo ACCESS EXCLUSIVE)'
VACUUM (FULL, ANALYZE) reserva;
\echo '--- Después'
SELECT pg_size_pretty(pg_relation_size('reserva')) AS tabla, pg_size_pretty(pg_indexes_size('reserva')) AS indices;
SELECT indexrelid::regclass AS indice, pg_size_pretty(pg_relation_size(indexrelid)) AS tam
  FROM pg_index WHERE indrelid = 'reserva'::regclass ORDER BY pg_relation_size(indexrelid) DESC;
VACUUM reserva;
