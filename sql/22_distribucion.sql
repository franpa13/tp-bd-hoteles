-- =====================================================================
-- Script 22: análisis de la distribución de los datos (Punto 21)
-- =====================================================================
SET search_path TO hotel, public;
\pset pager off
SET max_parallel_workers_per_gather = 0;

\echo '--- Reservas por estado'
SELECT estado, count(*), round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct FROM reserva GROUP BY 1 ORDER BY 2 DESC;

\echo '--- Reservas por año'
SELECT extract(year FROM fecha_inicio)::int AS anio, count(*) FROM reserva GROUP BY 1 ORDER BY 1;

\echo '--- Estacionalidad: reservas por mes de inicio (2016-2025)'
SELECT extract(month FROM fecha_inicio)::int AS mes, count(*) FROM reserva
 WHERE fecha_inicio >= '2016-01-01' AND fecha_inicio < '2026-01-01' GROUP BY 1 ORDER BY 1;

\echo '--- Duración de las estadías'
SELECT fecha_fin - fecha_inicio AS noches, count(*), round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
  FROM reserva GROUP BY 1 ORDER BY 1;

\echo '--- Concentración por huésped: reservas por huésped'
WITH x AS (SELECT huesped_id, count(*) AS n FROM reserva GROUP BY huesped_id)
SELECT count(*) AS huespedes_con_reserva,
       (SELECT count(*) FROM huesped) - count(*) AS huespedes_sin_reserva,
       max(n) AS maximo, round(avg(n), 1) AS promedio,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY n) AS mediana
  FROM x;
WITH x AS (SELECT huesped_id, count(*) AS n FROM reserva GROUP BY huesped_id),
     r AS (SELECT n, ntile(10) OVER (ORDER BY n DESC) AS decil FROM x)
SELECT decil, sum(n) AS reservas, round(100.0 * sum(n) / (SELECT count(*) FROM reserva), 1) AS pct_del_total
  FROM r GROUP BY decil ORDER BY decil;

\echo '--- Concentración por hotel: los 5 más y los 5 menos reservados'
(SELECT h.hotel_id, h.nombre, h.categoria, count(*) AS reservas
   FROM reserva r JOIN habitacion hb USING (habitacion_id) JOIN hotel h USING (hotel_id)
  GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 5)
UNION ALL
(SELECT h.hotel_id, h.nombre, h.categoria, count(*)
   FROM reserva r JOIN habitacion hb USING (habitacion_id) JOIN hotel h USING (hotel_id)
  GROUP BY 1, 2, 3 ORDER BY 4 ASC LIMIT 5);

\echo '--- Apellidos más y menos frecuentes (sesgo de la distribución)'
(SELECT apellido, count(*) FROM huesped GROUP BY 1 ORDER BY 2 DESC LIMIT 5)
UNION ALL
(SELECT apellido, count(*) FROM huesped GROUP BY 1 ORDER BY 2 ASC LIMIT 5);

\echo '--- Lo que ve el optimizador: valores más comunes de estado'
SELECT most_common_vals, most_common_freqs FROM pg_stats WHERE tablename = 'reserva' AND attname = 'estado';

\echo '--- Consecuencia del sesgo: mismo SQL, distinto plan según el valor'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT count(*) FROM huesped WHERE apellido = 'González';
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT count(*) FROM huesped WHERE apellido = 'Paredes';
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT count(*), sum(tarifa_noche) FROM reserva WHERE huesped_id = 1;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT count(*), sum(tarifa_noche) FROM reserva WHERE huesped_id = 900000;
