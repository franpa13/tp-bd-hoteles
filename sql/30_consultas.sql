-- =====================================================================
-- Script 30: consultas del sistema (Parte V, Puntos 24 a 27)
-- Cada consulta va precedida de una línea "-- @ID Título" que usa
-- 31_correr_consultas.py para medirla. "Hoy" es la fecha fija 2026-10-11.
-- =====================================================================
SET search_path TO hotel, public;

-- ===================== PUNTO 24: dificultad progresiva =====================

-- @24.1 Fechas: reservas que comienzan hoy
SELECT reserva_id, habitacion_id, huesped_id, fecha_fin
  FROM reserva
 WHERE fecha_inicio = DATE '2026-10-11' AND estado IN ('C','P');

-- @24.2 INNER JOIN: huéspedes que ingresan hoy con su habitación
SELECT r.reserva_id, hu.apellido, hu.nombre, hb.numero AS habitacion, r.fecha_fin
  FROM reserva r
  JOIN huesped hu    ON hu.huesped_id = r.huesped_id
  JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
 WHERE r.fecha_inicio = DATE '2026-10-11' AND r.estado IN ('C','P')
 ORDER BY hu.apellido, hu.nombre;

-- @24.3 LEFT JOIN: huéspedes registrados en 2026 que todavía no reservaron
SELECT hu.huesped_id, hu.apellido, hu.nombre, hu.fecha_registro
  FROM huesped hu
  LEFT JOIN reserva r ON r.huesped_id = hu.huesped_id
 WHERE hu.fecha_registro >= TIMESTAMPTZ '2026-01-01 00:00-03'
   AND r.reserva_id IS NULL
 ORDER BY hu.fecha_registro DESC
 LIMIT 50;

-- @24.4 EXISTS: hoteles con alguna suite reservada para el próximo mes
SELECT h.hotel_id, h.nombre
  FROM hotel h
 WHERE EXISTS (SELECT 1
                 FROM habitacion hb JOIN reserva r ON r.habitacion_id = hb.habitacion_id
                WHERE hb.hotel_id = h.hotel_id AND hb.tipo_habitacion_id = 5
                  AND r.fecha_inicio >= '2026-11-01' AND r.fecha_inicio < '2026-12-01'
                  AND r.estado IN ('C','P'));

-- @24.5 CASE WHEN: clasificación de reservas de 2025 por duración
SELECT CASE WHEN fecha_fin - fecha_inicio = 1 THEN '1 noche'
            WHEN fecha_fin - fecha_inicio <= 3 THEN '2 a 3 noches'
            WHEN fecha_fin - fecha_inicio <= 7 THEN '4 a 7 noches'
            ELSE 'más de 7 noches' END AS duracion,
       count(*) AS reservas
  FROM reserva
 WHERE fecha_inicio >= '2025-01-01' AND fecha_inicio < '2026-01-01'
 GROUP BY 1 ORDER BY min(fecha_fin - fecha_inicio);

-- @24.6 GROUP BY + agregaciones: estadísticas por estado
SELECT e.descripcion, count(*) AS reservas,
       round(avg(r.fecha_fin - r.fecha_inicio), 2) AS noches_promedio,
       round(avg(r.tarifa_noche), 2) AS tarifa_promedio
  FROM reserva r JOIN estado_reserva e USING (estado)
 GROUP BY e.descripcion ORDER BY reservas DESC;

-- @24.7 ORDER BY + LIMIT: las 10 estadías más largas finalizadas
SELECT reserva_id, habitacion_id, fecha_inicio, fecha_fin, fecha_fin - fecha_inicio AS noches
  FROM reserva WHERE estado = 'F'
 ORDER BY noches DESC, fecha_inicio DESC LIMIT 10;

-- @24.8 Subconsulta escalar: reservas 2025 con tarifa mayor al promedio de su año
SELECT count(*)
  FROM reserva r
 WHERE r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01'
   AND r.tarifa_noche > (SELECT avg(tarifa_noche) FROM reserva
                          WHERE fecha_inicio >= '2025-01-01' AND fecha_inicio < '2026-01-01');

-- @24.9 Subconsulta en FROM + HAVING: huéspedes con más de 25 reservas
SELECT hu.huesped_id, hu.apellido, hu.nombre, t.reservas
  FROM (SELECT huesped_id, count(*) AS reservas FROM reserva GROUP BY huesped_id HAVING count(*) > 25) t
  JOIN huesped hu USING (huesped_id)
 ORDER BY t.reservas DESC LIMIT 20;

-- @24.10 Funciones de ventana: ranking de hoteles por reservas en 2025 dentro de su provincia
SELECT provincia, hotel, reservas, rank() OVER (PARTITION BY provincia ORDER BY reservas DESC) AS puesto
  FROM (SELECT p.nombre AS provincia, h.nombre AS hotel, count(*) AS reservas
          FROM reserva r
          JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
          JOIN hotel h       ON h.hotel_id = hb.hotel_id
          JOIN domicilio d   ON d.domicilio_id = h.domicilio_id
          JOIN localidad l   ON l.localidad_id = d.localidad_id
          JOIN provincia p   ON p.provincia_id = l.provincia_id
         WHERE r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01' AND r.estado = 'F'
         GROUP BY p.nombre, h.nombre) t
 ORDER BY provincia, puesto;

-- ===================== PUNTO 25: consultas complejas =====================

-- @25.1 Disponibilidad: habitaciones dobles libres en Bariloche del 10 al 17/01/2027 (5 tablas)
SELECT h.nombre AS hotel, hb.numero, hb.piso, th.nombre AS tipo
  FROM habitacion hb
  JOIN tipo_habitacion th ON th.tipo_habitacion_id = hb.tipo_habitacion_id
  JOIN hotel h            ON h.hotel_id = hb.hotel_id
  JOIN domicilio d        ON d.domicilio_id = h.domicilio_id
  JOIN localidad l        ON l.localidad_id = d.localidad_id
 WHERE l.nombre = 'San Carlos de Bariloche' AND th.nombre = 'Doble' AND hb.activa
   AND NOT EXISTS (SELECT 1 FROM reserva r
                    WHERE r.habitacion_id = hb.habitacion_id AND r.estado IN ('P','C','F')
                      AND daterange(r.fecha_inicio, r.fecha_fin, '[)') && daterange('2027-01-10', '2027-01-17', '[)'))
 ORDER BY h.nombre, hb.numero;

-- @25.2 Reservas por período: reservas confirmadas de diciembre 2026 con huésped y hotel (4 tablas)
SELECT r.reserva_id, h.nombre AS hotel, hb.numero, hu.apellido || ', ' || hu.nombre AS huesped,
       r.fecha_inicio, r.fecha_fin, r.tarifa_noche
  FROM reserva r
  JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
  JOIN hotel h       ON h.hotel_id = hb.hotel_id
  JOIN huesped hu    ON hu.huesped_id = r.huesped_id
 WHERE r.fecha_inicio >= '2026-12-01' AND r.fecha_inicio < '2027-01-01' AND r.estado = 'C'
 ORDER BY r.fecha_inicio, h.nombre
 LIMIT 100;

-- @25.3 Top 10 hoteles con más reservas finalizadas en 2025
SELECT h.nombre, h.categoria, count(*) AS reservas
  FROM reserva r
  JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
  JOIN hotel h       ON h.hotel_id = hb.hotel_id
 WHERE r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01' AND r.estado = 'F'
 GROUP BY h.hotel_id ORDER BY reservas DESC LIMIT 10;

-- @25.4 Ocupación mensual 2025 por hotel (noches vendidas / noches disponibles)
WITH cap AS (SELECT hotel_id, count(*) AS habitaciones FROM habitacion GROUP BY hotel_id),
     noches AS (
       SELECT hb.hotel_id, date_trunc('month', g)::date AS mes, count(*) AS noches_ocupadas
         FROM reserva r
         JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
         CROSS JOIN LATERAL generate_series(r.fecha_inicio, r.fecha_fin - 1, INTERVAL '1 day') g
        WHERE r.estado = 'F' AND r.fecha_inicio < '2026-01-01' AND r.fecha_fin > '2025-01-01'
          AND g >= '2025-01-01' AND g < '2026-01-01'
        GROUP BY 1, 2)
SELECT h.nombre, n.mes,
       round(100.0 * n.noches_ocupadas / (c.habitaciones * extract(day FROM (n.mes + INTERVAL '1 month' - INTERVAL '1 day'))), 1) AS ocupacion_pct
  FROM noches n JOIN cap c USING (hotel_id) JOIN hotel h USING (hotel_id)
 ORDER BY h.nombre, n.mes;

-- @25.5 Facturación anual por provincia y categoría (6 tablas)
SELECT p.nombre AS provincia, h.categoria, extract(year FROM r.fecha_inicio)::int AS anio,
       sum(r.tarifa_noche * (r.fecha_fin - r.fecha_inicio)) AS facturado_usd
  FROM reserva r
  JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
  JOIN hotel h       ON h.hotel_id = hb.hotel_id
  JOIN domicilio d   ON d.domicilio_id = h.domicilio_id
  JOIN localidad l   ON l.localidad_id = d.localidad_id
  JOIN provincia p   ON p.provincia_id = l.provincia_id
 WHERE r.estado = 'F' AND r.fecha_inicio >= '2023-01-01' AND r.fecha_inicio < '2026-01-01'
 GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- @25.6 Historial de un huésped con hotel, localidad y comodidades de la habitación (6 tablas)
SELECT r.fecha_inicio, r.fecha_fin, e.descripcion AS estado, h.nombre AS hotel, l.nombre AS localidad,
       string_agg(co.nombre, ', ' ORDER BY co.nombre) AS comodidades
  FROM reserva r
  JOIN estado_reserva e ON e.estado = r.estado
  JOIN habitacion hb    ON hb.habitacion_id = r.habitacion_id
  JOIN hotel h          ON h.hotel_id = hb.hotel_id
  JOIN domicilio d      ON d.domicilio_id = h.domicilio_id
  JOIN localidad l      ON l.localidad_id = d.localidad_id
  LEFT JOIN habitacion_comodidad hc ON hc.habitacion_id = hb.habitacion_id
  LEFT JOIN comodidad co ON co.comodidad_id = hc.comodidad_id
 WHERE r.huesped_id = 1234
 GROUP BY r.reserva_id, e.descripcion, h.nombre, l.nombre
 ORDER BY r.fecha_inicio DESC;

-- @25.7 Huéspedes frecuentes: más de 5 provincias distintas visitadas (5 tablas)
SELECT hu.huesped_id, hu.apellido, hu.nombre, count(DISTINCT l.provincia_id) AS provincias, count(*) AS estadias
  FROM reserva r
  JOIN huesped hu    ON hu.huesped_id = r.huesped_id
  JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
  JOIN hotel h       ON h.hotel_id = hb.hotel_id
  JOIN domicilio d   ON d.domicilio_id = h.domicilio_id
  JOIN localidad l   ON l.localidad_id = d.localidad_id
 WHERE r.estado = 'F' AND r.huesped_id <= 2000
 GROUP BY hu.huesped_id
HAVING count(DISTINCT l.provincia_id) > 5
 ORDER BY provincias DESC, estadias DESC LIMIT 20;

-- @25.8 Puntos de interés a menos de 2 km de hoteles 5 estrellas, con tipo (4 tablas)
SELECT h.nombre AS hotel, t.nombre AS tipo, p.nombre AS punto, hp.distancia_m
  FROM hotel h
  JOIN hotel_punto_interes hp ON hp.hotel_id = h.hotel_id
  JOIN punto_interes p        ON p.punto_interes_id = hp.punto_interes_id
  JOIN tipo_punto_interes t   ON t.tipo_punto_interes_id = p.tipo_punto_interes_id
 WHERE h.categoria = 5 AND hp.distancia_m < 2000
 ORDER BY h.nombre, hp.distancia_m;

-- @25.9 Tasa de cancelación y no-show por hotel en 2025
SELECT h.nombre,
       count(*) AS reservas,
       round(100.0 * count(*) FILTER (WHERE r.estado = 'X') / count(*), 2) AS cancelacion_pct,
       round(100.0 * count(*) FILTER (WHERE r.estado = 'N') / count(*), 2) AS no_show_pct
  FROM reserva r JOIN habitacion hb USING (habitacion_id) JOIN hotel h USING (hotel_id)
 WHERE r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01'
 GROUP BY h.hotel_id ORDER BY cancelacion_pct DESC LIMIT 10;

-- @25.10 Anticipación promedio de reserva por temporada (análisis temporal)
SELECT CASE WHEN extract(month FROM fecha_inicio) IN (1,2,7) THEN 'alta'
            WHEN extract(month FROM fecha_inicio) IN (3,10,12) THEN 'media' ELSE 'baja' END AS temporada,
       round(avg(fecha_inicio - fecha_creacion::date), 1) AS dias_anticipacion,
       count(*) AS reservas
  FROM reserva
 WHERE fecha_inicio >= '2024-01-01' AND fecha_inicio < '2026-01-01'
 GROUP BY 1 ORDER BY 2 DESC;

-- @25.11 Evolución interanual de reservas por mes con variación (LAG)
SELECT anio, mes, reservas,
       round(100.0 * (reservas - lag(reservas) OVER (PARTITION BY mes ORDER BY anio))
             / lag(reservas) OVER (PARTITION BY mes ORDER BY anio), 1) AS variacion_pct
  FROM (SELECT extract(year FROM fecha_inicio)::int AS anio, extract(month FROM fecha_inicio)::int AS mes, count(*) AS reservas
          FROM reserva WHERE fecha_inicio >= '2022-01-01' AND fecha_inicio < '2026-01-01'
         GROUP BY 1, 2) t
 ORDER BY mes, anio;

-- @25.12 Ingreso por tipo de habitación y comparación con la tarifa de lista (5 tablas)
SELECT th.nombre AS tipo, h.categoria,
       round(avg(r.tarifa_noche), 2) AS tarifa_pactada,
       round(avg(t.precio_noche), 2)  AS tarifa_lista,
       round(100.0 * (avg(r.tarifa_noche) - avg(t.precio_noche)) / avg(t.precio_noche), 1) AS desvio_pct
  FROM reserva r
  JOIN habitacion hb      ON hb.habitacion_id = r.habitacion_id
  JOIN hotel h            ON h.hotel_id = hb.hotel_id
  JOIN tipo_habitacion th ON th.tipo_habitacion_id = hb.tipo_habitacion_id
  JOIN tarifa t           ON t.hotel_id = h.hotel_id AND t.tipo_habitacion_id = hb.tipo_habitacion_id
                         AND r.fecha_inicio >= t.vigencia_desde AND r.fecha_inicio < t.vigencia_hasta
 WHERE r.estado = 'F' AND r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01'
 GROUP BY th.nombre, h.categoria ORDER BY h.categoria, th.nombre;

-- @25.13 Huéspedes extranjeros por país de origen y destino preferido (6 tablas)
SELECT pa.nombre AS pais_origen, l.nombre AS destino, count(*) AS estadias,
       rank() OVER (PARTITION BY pa.nombre ORDER BY count(*) DESC) AS puesto
  FROM reserva r
  JOIN huesped hu    ON hu.huesped_id = r.huesped_id
  JOIN pais pa       ON pa.pais_id = hu.nacionalidad_id
  JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
  JOIN hotel h       ON h.hotel_id = hb.hotel_id
  JOIN domicilio d   ON d.domicilio_id = h.domicilio_id
  JOIN localidad l   ON l.localidad_id = d.localidad_id
 WHERE pa.codigo_iso <> 'AR' AND r.estado = 'F' AND r.fecha_inicio >= '2025-01-01' AND r.fecha_inicio < '2026-01-01'
 GROUP BY pa.nombre, l.nombre
 ORDER BY pa.nombre, puesto;

-- @25.14 Habitaciones sin ninguna reserva en los últimos 90 días (posibles fuera de servicio)
SELECT h.nombre, hb.numero
  FROM habitacion hb JOIN hotel h USING (hotel_id)
 WHERE NOT EXISTS (SELECT 1 FROM reserva r
                    WHERE r.habitacion_id = hb.habitacion_id
                      AND r.fecha_inicio >= DATE '2026-10-11' - 90 AND r.fecha_inicio < DATE '2026-10-11')
 ORDER BY 1, 2;

-- @25.15 Huéspedes en casa hoy: check-out mañana con teléfono principal (4 tablas)
SELECT h.nombre AS hotel, hb.numero, hu.apellido, hu.nombre, tel.numero AS telefono
  FROM reserva r
  JOIN habitacion hb ON hb.habitacion_id = r.habitacion_id
  JOIN hotel h       ON h.hotel_id = hb.hotel_id
  JOIN huesped hu    ON hu.huesped_id = r.huesped_id
  LEFT JOIN huesped_telefono tel ON tel.huesped_id = hu.huesped_id AND tel.principal
 WHERE r.fecha_fin = DATE '2026-10-12' AND r.fecha_inicio <= DATE '2026-10-11' AND r.estado IN ('C','F')
 ORDER BY h.nombre, hb.numero;

-- ===================== PUNTO 26: disponibilidad =====================

-- @26.1 ¿Está libre la habitación 1234 del 2 al 6/07/2026? (comparación explícita)
SELECT NOT EXISTS (
  SELECT 1 FROM reserva
   WHERE habitacion_id = 1234 AND estado IN ('P','C','F')
     AND fecha_inicio < DATE '2026-07-06'   -- empieza antes de que yo me vaya
     AND fecha_fin    > DATE '2026-07-02'   -- termina después de que yo llegue
) AS disponible;

-- @26.2 Misma pregunta con rangos (usa el índice GiST de la restricción)
SELECT NOT EXISTS (
  SELECT 1 FROM reserva
   WHERE habitacion_id = 1234 AND estado IN ('P','C','F')
     AND daterange(fecha_inicio, fecha_fin, '[)') && daterange('2026-07-02', '2026-07-06', '[)')
) AS disponible;

-- @26.3 Versión errónea (sólo mira si la llegada cae dentro de otra reserva)
SELECT NOT EXISTS (
  SELECT 1 FROM reserva
   WHERE habitacion_id = 1234 AND estado IN ('P','C','F')
     AND DATE '2026-07-02' BETWEEN fecha_inicio AND fecha_fin
) AS disponible_mal;

-- @26.4 Cantidad de habitaciones libres por tipo en un hotel para un período
SELECT th.nombre, count(*) AS libres
  FROM habitacion hb JOIN tipo_habitacion th USING (tipo_habitacion_id)
 WHERE hb.hotel_id = 13
   AND NOT EXISTS (SELECT 1 FROM reserva r
                    WHERE r.habitacion_id = hb.habitacion_id AND r.estado IN ('P','C','F')
                      AND daterange(r.fecha_inicio, r.fecha_fin, '[)') && daterange('2027-02-01','2027-02-08','[)'))
 GROUP BY th.nombre ORDER BY th.nombre;

-- ===================== PUNTO 27: consultas temporales =====================

-- @27.1 Reservas futuras (desde hoy) por estado
SELECT estado, count(*) FROM reserva WHERE fecha_inicio >= DATE '2026-10-11' GROUP BY estado;

-- @27.2 Históricas por año
SELECT extract(year FROM fecha_inicio)::int AS anio, count(*) FROM reserva
 WHERE fecha_inicio < DATE '2026-10-11' GROUP BY 1 ORDER BY 1;

-- @27.3 Por mes de 2025 (agrupando con date_trunc)
SELECT date_trunc('month', fecha_inicio)::date AS mes, count(*) FROM reserva
 WHERE fecha_inicio >= '2025-01-01' AND fecha_inicio < '2026-01-01' GROUP BY 1 ORDER BY 1;

-- @27.4 Estadías que se solapan con un rango (no sólo las que empiezan en él)
SELECT count(*) FROM reserva
 WHERE fecha_inicio < '2025-08-01' AND fecha_fin > '2025-07-01' AND estado = 'F';

-- @27.5a Filtro de año con EXTRACT (no SARGable)
SELECT count(*) FROM reserva WHERE extract(year FROM fecha_inicio) = 2024;

-- @27.5b Filtro de año con rango semiabierto (SARGable)
SELECT count(*) FROM reserva WHERE fecha_inicio >= '2024-01-01' AND fecha_inicio < '2025-01-01';

-- @27.5c Filtro de año con BETWEEN
SELECT count(*) FROM reserva WHERE fecha_inicio BETWEEN '2024-01-01' AND '2024-12-31';

-- @27.5d Filtro con to_char (no SARGable, además compara texto)
SELECT count(*) FROM reserva WHERE to_char(fecha_inicio, 'YYYY') = '2024';

-- @27.6a Mes con date_trunc sobre la columna
SELECT count(*) FROM reserva WHERE date_trunc('month', fecha_inicio) = '2024-07-01';

-- @27.6b Mes con rango
SELECT count(*) FROM reserva WHERE fecha_inicio >= '2024-07-01' AND fecha_inicio < '2024-08-01';
