-- =====================================================================
-- Script 02: datos mínimos + pruebas de las reglas de negocio.
-- Cada bloque DO intenta violar una regla y muestra si la base la rechaza.
-- Ejecutar después de 01_schema.sql:  psql -d hoteles -f 02_pruebas_integridad.sql
-- =====================================================================
SET search_path TO hotel, public;

INSERT INTO pais (codigo_iso, nombre) VALUES ('AR','Argentina');
INSERT INTO provincia (pais_id, nombre) VALUES (1,'Jujuy');
INSERT INTO localidad (provincia_id, nombre, codigo_postal) VALUES (1,'San Salvador de Jujuy','4600');
INSERT INTO domicilio (localidad_id, calle, numero) VALUES (1,'Belgrano','500'), (1,'Alvear','1200');
INSERT INTO hotel (nombre, categoria, domicilio_id) VALUES ('Hotel Prueba', 4, 1);
INSERT INTO tipo_habitacion (nombre, capacidad_maxima) VALUES ('Doble', 2);
INSERT INTO habitacion (hotel_id, tipo_habitacion_id, numero, piso) VALUES (1,1,'101',1);
INSERT INTO huesped (tipo_documento, numero_documento, nombre, apellido, domicilio_id)
VALUES ('DNI','30111222','Ana','Pérez', 2);

-- Reserva base: 10 al 15 de marzo
INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin)
VALUES (1, 1, '2027-03-10', '2027-03-15');

CREATE TEMP TABLE resultado (prueba TEXT, esperado TEXT, obtenido TEXT);

CREATE FUNCTION pg_temp.probar(p_nombre TEXT, p_sql TEXT, p_esperado TEXT)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE p_sql;
        INSERT INTO resultado VALUES (p_nombre, p_esperado, 'ACEPTADA');
    EXCEPTION WHEN OTHERS THEN
        INSERT INTO resultado VALUES (p_nombre, p_esperado, 'RECHAZADA: ' || SQLERRM);
    END;
END $$;

\o /dev/null
SELECT pg_temp.probar('1. Reserva superpuesta (12 al 18)',
  $q$INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin)
     VALUES (1,1,'2027-03-12','2027-03-18')$q$, 'RECHAZADA');

SELECT pg_temp.probar('2. Reserva contigua (entra el día que sale la otra)',
  $q$INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin)
     VALUES (1,1,'2027-03-15','2027-03-17')$q$, 'ACEPTADA');

SELECT pg_temp.probar('3. Fecha de salida anterior a la de inicio',
  $q$INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin)
     VALUES (1,1,'2027-04-10','2027-04-05')$q$, 'RECHAZADA');

SELECT pg_temp.probar('4. Pendiente con tarifa cargada',
  $q$INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin, tarifa_noche)
     VALUES (1,1,'2027-05-01','2027-05-03', 50000)$q$, 'RECHAZADA');

SELECT pg_temp.probar('5. Confirmar sin tarifa',
  $q$UPDATE reserva SET estado='C', fecha_confirmacion=now() WHERE reserva_id=1$q$, 'RECHAZADA');

SELECT pg_temp.probar('6. Confirmar con tarifa',
  $q$UPDATE reserva SET estado='C', fecha_confirmacion=now(), tarifa_noche=85000 WHERE reserva_id=1$q$, 'ACEPTADA');

SELECT pg_temp.probar('7. Más huéspedes que la capacidad',
  $q$INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin, cantidad_huespedes)
     VALUES (1,1,'2027-06-01','2027-06-03', 3)$q$, 'RECHAZADA');

SELECT pg_temp.probar('8. Cancelada que se superpone (libera la habitación)',
  $q$INSERT INTO reserva (habitacion_id, huesped_id, fecha_inicio, fecha_fin, estado)
     VALUES (1,1,'2027-03-11','2027-03-13','X')$q$, 'ACEPTADA');

SELECT pg_temp.probar('9. Huésped con documento duplicado',
  $q$INSERT INTO huesped (tipo_documento, numero_documento, nombre, apellido)
     VALUES ('DNI','30111222','Otro','Nombre')$q$, 'RECHAZADA');

SELECT pg_temp.probar('10. Dos emails principales para el mismo huésped',
  $q$INSERT INTO huesped_email (huesped_id, email, principal)
     VALUES (1,'ana@mail.com',TRUE),(1,'ana2@mail.com',TRUE)$q$, 'RECHAZADA');

SELECT pg_temp.probar('11. Email con formato inválido',
  $q$INSERT INTO huesped_email (huesped_id, email) VALUES (1,'ana-arroba-mail')$q$, 'RECHAZADA');

SELECT pg_temp.probar('12. Tarifas de lista con vigencias solapadas',
  $q$INSERT INTO tarifa (hotel_id, tipo_habitacion_id, vigencia_desde, vigencia_hasta, precio_noche)
     VALUES (1,1,'2027-01-01','2027-07-01',80000),(1,1,'2027-06-01',NULL,90000)$q$, 'RECHAZADA');

SELECT pg_temp.probar('13. Borrar huésped con reservas (integridad referencial)',
  $q$DELETE FROM huesped WHERE huesped_id=1$q$, 'RECHAZADA');

SELECT pg_temp.probar('14. Hotel con 6 estrellas',
  $q$INSERT INTO hotel (nombre, categoria, domicilio_id) VALUES ('X', 6, 2)$q$, 'RECHAZADA');

\o
SELECT prueba,
       esperado,
       CASE WHEN obtenido LIKE esperado || '%' THEN 'OK' ELSE 'FALLA' END AS veredicto,
       obtenido
  FROM resultado;
