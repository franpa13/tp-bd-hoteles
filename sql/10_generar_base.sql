-- =====================================================================
-- Script 10: generación reproducible de datos maestros
-- (ubicación, hoteles, habitaciones, comodidades, tarifas, puntos de
--  interés y 1.000.000 de huéspedes con sus contactos y domicilios).
-- Las reservas las genera 11_generar_reservas.py.
-- Reproducible: setseed() fija la secuencia de random() de la sesión.
-- Ejecutar sobre un esquema recién creado con 01_schema.sql.
-- =====================================================================
SET search_path TO hotel, public;
\timing on
SELECT setseed(0.42);

-- ---------- Países (para nacionalidad) ----------
INSERT INTO pais (codigo_iso, nombre) VALUES
 ('AR','Argentina'),('BR','Brasil'),('CL','Chile'),('UY','Uruguay'),('PY','Paraguay'),
 ('BO','Bolivia'),('US','Estados Unidos'),('ES','España'),('DE','Alemania'),('FR','Francia');

-- ---------- Provincias y localidades turísticas ----------
INSERT INTO provincia (pais_id, nombre)
SELECT 1, p FROM unnest(ARRAY['Ciudad Autónoma de Buenos Aires','Buenos Aires','Córdoba','Mendoza',
  'Salta','Jujuy','Río Negro','Neuquén','Misiones','Tierra del Fuego','Santa Cruz','Chubut',
  'Tucumán','Santa Fe','Entre Ríos']) WITH ORDINALITY AS t(p, o) ORDER BY o;

-- peso = cantidad de hoteles de la cadena en esa localidad
CREATE TEMP TABLE loc_def (prov TEXT, loc TEXT, cp TEXT, peso INT, lat NUMERIC, lon NUMERIC);
INSERT INTO loc_def VALUES
 ('Ciudad Autónoma de Buenos Aires','Buenos Aires','C1000',25,-34.6037,-58.3816),
 ('Buenos Aires','Mar del Plata','B7600',8,-38.0055,-57.5426),
 ('Córdoba','Córdoba','X5000',8,-31.4201,-64.1888),
 ('Córdoba','Villa Carlos Paz','X5152',4,-31.4241,-64.4978),
 ('Mendoza','Mendoza','M5500',10,-32.8895,-68.8458),
 ('Mendoza','San Rafael','M5600',2,-34.6177,-68.3301),
 ('Salta','Salta','A4400',8,-24.7821,-65.4232),
 ('Salta','Cafayate','A4427',2,-26.0730,-65.9761),
 ('Jujuy','San Salvador de Jujuy','Y4600',6,-24.1858,-65.2995),
 ('Jujuy','Purmamarca','Y4618',2,-23.7447,-65.4986),
 ('Jujuy','Tilcara','Y4624',2,-23.5770,-65.3963),
 ('Jujuy','Humahuaca','Y4630',1,-23.2054,-65.3505),
 ('Río Negro','San Carlos de Bariloche','R8400',12,-41.1335,-71.3103),
 ('Neuquén','San Martín de los Andes','Q8370',3,-40.1579,-71.3534),
 ('Misiones','Puerto Iguazú','N3370',7,-25.5991,-54.5736),
 ('Tierra del Fuego','Ushuaia','V9410',6,-54.8019,-68.3030),
 ('Santa Cruz','El Calafate','Z9405',5,-50.3379,-72.2648),
 ('Chubut','Puerto Madryn','U9120',3,-42.7692,-65.0385),
 ('Tucumán','San Miguel de Tucumán','T4000',3,-26.8083,-65.2176),
 ('Santa Fe','Rosario','S2000',4,-32.9442,-60.6505),
 ('Entre Ríos','Colón','E3280',2,-32.2234,-58.1426);

INSERT INTO localidad (provincia_id, nombre, codigo_postal)
SELECT p.provincia_id, d.loc, d.cp FROM loc_def d JOIN provincia p ON p.nombre = d.prov;

-- ---------- Catálogos ----------
INSERT INTO tipo_habitacion (nombre, capacidad_maxima, descripcion) VALUES
 ('Single',1,'Una cama individual'),('Doble',2,'Cama matrimonial o dos individuales'),
 ('Triple',3,'Tres camas'),('Cuádruple',4,'Dos camas matrimoniales'),
 ('Suite',4,'Ambiente separado con living'),('Familiar',6,'Dos ambientes');

INSERT INTO comodidad (nombre) SELECT unnest(ARRAY['Wi-Fi','Aire acondicionado','Calefacción',
 'TV por cable','Minibar','Caja fuerte','Balcón','Vista panorámica','Bañera de hidromasaje',
 'Cafetera','Escritorio','Accesible silla de ruedas']);

INSERT INTO tipo_punto_interes (nombre) SELECT unnest(ARRAY['Museo','Parque','Aeropuerto',
 'Terminal de ómnibus','Centro comercial','Mirador','Iglesia','Playa','Centro de esquí','Reserva natural']);

-- ---------- Hoteles (123) ----------
INSERT INTO domicilio (localidad_id, calle, numero, codigo_postal)
SELECT l.localidad_id,
       (ARRAY['Av. San Martín','Belgrano','Av. Costanera','Mitre','Rivadavia','Sarmiento','Av. Libertador','Güemes'])[1 + floor(random()*8)::int],
       (100 + floor(random()*2900))::int::text, d.cp
  FROM loc_def d JOIN localidad l ON l.nombre = d.loc
  CROSS JOIN LATERAL generate_series(1, d.peso) g
 ORDER BY l.localidad_id, g;

INSERT INTO hotel (nombre, categoria, descripcion, domicilio_id, latitud, longitud, fecha_alta)
SELECT 'Hotel ' || l.nombre || ' ' || row_number() OVER (PARTITION BY l.localidad_id ORDER BY dm.domicilio_id),
       -- categoría: más 3 y 4 estrellas
       (ARRAY[2,3,3,3,4,4,4,5])[1 + floor(random()*8)::int],
       'Hotel de la cadena en ' || l.nombre,
       dm.domicilio_id,
       round(d.lat + (random()-0.5)::numeric*0.04, 6), round(d.lon + (random()-0.5)::numeric*0.04, 6),
       DATE '2010-01-01' + floor(random()*1500)::int
  FROM domicilio dm JOIN localidad l USING (localidad_id) JOIN loc_def d ON d.loc = l.nombre
 ORDER BY dm.domicilio_id;

INSERT INTO hotel_contacto (hotel_id, tipo_contacto_id, valor, principal)
SELECT hotel_id, 1, '+54 ' || (200 + hotel_id) || ' ' || (4000000 + hotel_id*37), TRUE FROM hotel
UNION ALL
SELECT hotel_id, 2, 'reservas.h' || hotel_id || '@cadenahoteles.com.ar', TRUE FROM hotel
UNION ALL
SELECT hotel_id, 3, 'https://cadenahoteles.com.ar/h' || hotel_id, TRUE FROM hotel
UNION ALL
SELECT hotel_id, 4, '+54 9 ' || (200 + hotel_id) || ' ' || (5000000 + hotel_id*41), TRUE FROM hotel WHERE random() < 0.7;

-- ---------- Habitaciones: cantidad según categoría ----------
INSERT INTO habitacion (hotel_id, tipo_habitacion_id, numero, piso)
SELECT h.hotel_id,
       CASE WHEN r < 0.10 THEN 1 WHEN r < 0.60 THEN 2 WHEN r < 0.75 THEN 3
            WHEN r < 0.87 THEN 4 WHEN r < 0.93 THEN 5 ELSE 6 END,
       ((n - 1) / 20 + 1)::text || lpad(((n - 1) % 20 + 1)::text, 2, '0'),
       (n - 1) / 20 + 1
  FROM hotel h
  CROSS JOIN LATERAL generate_series(1,
       CASE h.categoria WHEN 2 THEN 15 + floor(random()*15)::int
                        WHEN 3 THEN 30 + floor(random()*30)::int
                        WHEN 4 THEN 50 + floor(random()*50)::int
                        ELSE 80 + floor(random()*70)::int END) n
  CROSS JOIN LATERAL (SELECT random() + n*0 AS r) x;

-- Comodidades: Wi-Fi y calefacción en todas; el resto según categoría
INSERT INTO habitacion_comodidad (habitacion_id, comodidad_id)
SELECT hb.habitacion_id, c.comodidad_id
  FROM habitacion hb JOIN hotel h USING (hotel_id) CROSS JOIN comodidad c
 WHERE c.comodidad_id IN (1,3)
    OR random() < 0.10 + 0.15 * h.categoria + CASE WHEN hb.tipo_habitacion_id = 5 THEN 0.3 ELSE 0 END;

-- ---------- Tarifas de lista: una por año, hotel y tipo (USD) ----------
INSERT INTO tarifa (hotel_id, tipo_habitacion_id, vigencia_desde, vigencia_hasta, precio_noche)
SELECT h.hotel_id, t.tipo_habitacion_id, make_date(y,1,1), make_date(y+1,1,1),
       round((ARRAY[35,50,80,130,220])[h.categoria]
             * (ARRAY[0.8,1,1.25,1.45,2.2,1.7])[t.tipo_habitacion_id]
             * (1 + 0.03*(y-2015)), 2)
  FROM hotel h CROSS JOIN tipo_habitacion t CROSS JOIN generate_series(2015, 2027) y;

-- ---------- Puntos de interés (6 por localidad) y relación con hoteles ----------
INSERT INTO punto_interes (tipo_punto_interes_id, localidad_id, nombre, latitud, longitud)
SELECT 1 + ((l.localidad_id + g) % 10), l.localidad_id,
       (ARRAY['Museo','Parque','Aeropuerto','Terminal','Shopping','Mirador','Catedral','Playa','Cerro','Reserva'])[1 + ((l.localidad_id + g) % 10)]
         || ' de ' || l.nombre || ' ' || g,
       round(d.lat + (random()-0.5)::numeric*0.1, 6), round(d.lon + (random()-0.5)::numeric*0.1, 6)
  FROM localidad l JOIN loc_def d ON d.loc = l.nombre CROSS JOIN generate_series(1, 6) g;

INSERT INTO hotel_punto_interes (hotel_id, punto_interes_id, distancia_m)
SELECT h.hotel_id, p.punto_interes_id, (200 + random()*9800)::int
  FROM hotel h JOIN domicilio d USING (domicilio_id)
  JOIN punto_interes p ON p.localidad_id = d.localidad_id
 WHERE random() < 0.7;

-- ---------- Huéspedes (1.000.000) ----------
CREATE TEMP TABLE nombres AS SELECT unnest(ARRAY['Juan','María','José','Ana','Carlos','Laura','Luis',
 'Sofía','Jorge','Lucía','Miguel','Valentina','Diego','Camila','Pablo','Martina','Javier','Julieta',
 'Fernando','Florencia','Ricardo','Paula','Sergio','Carolina','Martín','Daniela','Alejandro','Romina',
 'Gustavo','Natalia','Facundo','Agustina','Matías','Micaela','Nicolás','Gabriela','Franco','Silvina',
 'Emiliano','Rocío']) AS n;
CREATE TEMP TABLE apellidos AS SELECT unnest(ARRAY['González','Rodríguez','Gómez','Fernández','López',
 'Díaz','Martínez','Pérez','García','Sánchez','Romero','Sosa','Torres','Álvarez','Ruiz','Ramírez',
 'Flores','Acosta','Benítez','Medina','Suárez','Herrera','Aguirre','Pereyra','Gutiérrez','Giménez',
 'Molina','Silva','Castro','Rojas','Ortiz','Núñez','Luna','Juárez','Cabrera','Ríos','Ferreyra',
 'Godoy','Morales','Domínguez','Quispe','Mamaní','Cruz','Vargas','Tolaba','Choque','Guzmán',
 'Paredes','Villalba','Ledesma']) AS a;
CREATE TEMP TABLE arr AS SELECT array_agg(n) AS n, (SELECT array_agg(a) FROM apellidos) AS a FROM nombres;

-- domicilios de huéspedes: localidades de la cadena (sesgado a Buenos Aires)
INSERT INTO domicilio (localidad_id, calle, numero, codigo_postal)
SELECT CASE WHEN random() < 0.45 THEN 1 ELSE 1 + floor(random()*21)::int END,
       (ARRAY['San Martín','Belgrano','Mitre','Rivadavia','Sarmiento','Moreno','Alberdi','Lavalle','Urquiza','Roca'])[1 + floor(random()*10)::int],
       (1 + floor(random()*4999))::int::text, NULL
  FROM generate_series(1, 1000000);

INSERT INTO huesped (tipo_documento, numero_documento, nombre, apellido, fecha_nacimiento,
                     nacionalidad_id, domicilio_id, fecha_registro)
SELECT CASE WHEN nac = 1 THEN 'DNI' ELSE 'PASAPORTE' END,
       CASE WHEN nac = 1 THEN (10000000 + g * 47)::text ELSE 'P' || lpad((g * 13)::text, 9, '0') END,
       arr.n[1 + floor(random()*40)::int],
       arr.a[1 + floor(power(random(), 1.6)*50)::int],          -- apellidos sesgados (algunos muy comunes)
       DATE '1945-01-01' + floor(random()*22000)::int,
       nac,
       (SELECT count(*) FROM hotel) + g,   -- los primeros domicilios son de los hoteles
       TIMESTAMPTZ '2014-06-01 00:00-03' + random() * INTERVAL '4400 days'
  FROM arr, generate_series(1, 1000000) g
  CROSS JOIN LATERAL (SELECT CASE WHEN random() < 0.85 + g*0 THEN 1 ELSE 2 + floor(random()*9)::int END AS nac) x;

INSERT INTO huesped_telefono (huesped_id, tipo, numero, principal)
SELECT huesped_id, 'MOVIL', '+54 9 ' || (11 + huesped_id % 380) || ' ' || (4000000 + huesped_id), TRUE FROM huesped
UNION ALL
SELECT huesped_id, 'FIJO', '+54 ' || (11 + huesped_id % 380) || ' ' || (3000000 + huesped_id), FALSE FROM huesped WHERE random() < 0.35;

INSERT INTO huesped_email (huesped_id, email, principal)
SELECT huesped_id, lower(translate(nombre || '.' || apellido, 'áéíóúÁÉÍÓÚñ ', 'aeiouAEIOUn')) || huesped_id || '@mail.com', TRUE
  FROM huesped WHERE random() < 0.92
UNION ALL
SELECT huesped_id, 'h' || huesped_id || '@trabajo.com.ar', FALSE FROM huesped WHERE random() < 0.15;

ANALYZE;
SELECT 'hotel' t, count(*) FROM hotel UNION ALL SELECT 'habitacion', count(*) FROM habitacion
UNION ALL SELECT 'huesped', count(*) FROM huesped UNION ALL SELECT 'huesped_telefono', count(*) FROM huesped_telefono
UNION ALL SELECT 'huesped_email', count(*) FROM huesped_email UNION ALL SELECT 'tarifa', count(*) FROM tarifa
UNION ALL SELECT 'punto_interes', count(*) FROM punto_interes UNION ALL SELECT 'hotel_punto_interes', count(*) FROM hotel_punto_interes
UNION ALL SELECT 'habitacion_comodidad', count(*) FROM habitacion_comodidad;
