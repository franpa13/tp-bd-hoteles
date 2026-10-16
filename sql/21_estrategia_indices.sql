-- =====================================================================
-- Script 21: estrategia general de índices (Punto 11).
-- Se aplica después de la carga masiva y antes de las Partes V a X.
-- Los índices de PK, UNIQUE, EXCLUDE y FK ya existen desde 01_schema.sql.
-- =====================================================================
SET search_path TO hotel, public;
\timing on

-- Consultas por período (reservas de un mes, de un año, ocupación)
CREATE INDEX IF NOT EXISTS ix_reserva_fecha_inicio ON reserva (fecha_inicio);

-- Búsqueda de huéspedes por apellido y nombre en recepción
CREATE INDEX IF NOT EXISTS ix_huesped_apellido_nombre ON huesped (apellido, nombre);

-- Altas recientes de huéspedes (reportes de registro)
CREATE INDEX IF NOT EXISTS ix_huesped_fecha_registro ON huesped (fecha_registro);

-- Login / búsqueda por email sin distinguir mayúsculas
CREATE INDEX IF NOT EXISTS ix_huesped_email_lower ON huesped_email (lower(email));

ANALYZE;

SELECT t.relname AS tabla, i.relname AS indice, am.amname AS tipo,
       pg_size_pretty(pg_relation_size(i.oid)) AS tam
  FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid JOIN pg_class t ON t.oid = x.indrelid
  JOIN pg_am am ON am.oid = i.relam
 WHERE t.relnamespace = 'hotel'::regnamespace
 ORDER BY pg_relation_size(i.oid) DESC;
