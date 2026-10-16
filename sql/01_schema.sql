-- =====================================================================
-- TP Diseño y Optimización de Bases de Datos — Cadena de hoteles
-- Script 01: creación completa del esquema (PostgreSQL 16)
-- Ejecutar con:  psql -d hoteles -f 01_schema.sql
-- =====================================================================

DROP SCHEMA IF EXISTS hotel CASCADE;
CREATE SCHEMA hotel;
SET search_path TO hotel, public;

-- btree_gist permite combinar "=" (habitación) y "&&" (rangos de fechas)
-- en una misma restricción EXCLUDE: es lo que impide reservas superpuestas.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------------
-- 1. Ubicación geográfica (jerarquía país > provincia > localidad)
-- ---------------------------------------------------------------------
CREATE TABLE pais (
    pais_id     SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_iso  CHAR(2)      NOT NULL UNIQUE CHECK (codigo_iso ~ '^[A-Z]{2}$'),
    nombre      VARCHAR(80)  NOT NULL UNIQUE
);

CREATE TABLE provincia (
    provincia_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pais_id      SMALLINT     NOT NULL REFERENCES pais(pais_id),
    nombre       VARCHAR(80)  NOT NULL,
    CONSTRAINT uq_provincia UNIQUE (pais_id, nombre)
);

CREATE TABLE localidad (
    localidad_id  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provincia_id  SMALLINT     NOT NULL REFERENCES provincia(provincia_id),
    nombre        VARCHAR(100) NOT NULL,
    codigo_postal VARCHAR(10),
    CONSTRAINT uq_localidad UNIQUE (provincia_id, nombre)
);

-- Domicilio: lo usan tanto hoteles como huéspedes (misma estructura)
CREATE TABLE domicilio (
    domicilio_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    localidad_id  INTEGER      NOT NULL REFERENCES localidad(localidad_id),
    calle         VARCHAR(120) NOT NULL,
    numero        VARCHAR(10)  NOT NULL,          -- admite "S/N", "1234 bis"
    piso          VARCHAR(5),
    departamento  VARCHAR(5),
    codigo_postal VARCHAR(10)
);

-- ---------------------------------------------------------------------
-- 2. Hoteles, contactos y puntos de interés
-- ---------------------------------------------------------------------
CREATE TABLE hotel (
    hotel_id      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre        VARCHAR(120)  NOT NULL UNIQUE,
    categoria     SMALLINT      NOT NULL CHECK (categoria BETWEEN 1 AND 5), -- estrellas
    descripcion   TEXT,
    domicilio_id  BIGINT        NOT NULL UNIQUE REFERENCES domicilio(domicilio_id),
    latitud       NUMERIC(9,6)  CHECK (latitud  BETWEEN -90  AND 90),
    longitud      NUMERIC(9,6)  CHECK (longitud BETWEEN -180 AND 180),
    hora_checkin  TIME          NOT NULL DEFAULT '14:00',
    hora_checkout TIME          NOT NULL DEFAULT '10:00',
    activo        BOOLEAN       NOT NULL DEFAULT TRUE,
    fecha_alta    DATE          NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE tipo_contacto (
    tipo_contacto_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre           VARCHAR(30) NOT NULL UNIQUE   -- TELEFONO, EMAIL, WEB, WHATSAPP...
);

CREATE TABLE hotel_contacto (
    hotel_contacto_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hotel_id          INTEGER      NOT NULL REFERENCES hotel(hotel_id) ON DELETE CASCADE,
    tipo_contacto_id  SMALLINT     NOT NULL REFERENCES tipo_contacto(tipo_contacto_id),
    valor             VARCHAR(150) NOT NULL,
    principal         BOOLEAN      NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_hotel_contacto UNIQUE (hotel_id, tipo_contacto_id, valor)
);
-- Un solo contacto principal por hotel y por tipo (índice UNIQUE parcial)
CREATE UNIQUE INDEX uq_hotel_contacto_principal
    ON hotel_contacto (hotel_id, tipo_contacto_id) WHERE principal;

CREATE TABLE tipo_punto_interes (
    tipo_punto_interes_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre                VARCHAR(50) NOT NULL UNIQUE  -- Museo, Aeropuerto, Parque...
);

CREATE TABLE punto_interes (
    punto_interes_id      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_punto_interes_id SMALLINT     NOT NULL REFERENCES tipo_punto_interes(tipo_punto_interes_id),
    localidad_id          INTEGER      NOT NULL REFERENCES localidad(localidad_id),
    nombre                VARCHAR(120) NOT NULL,
    descripcion           TEXT,
    latitud               NUMERIC(9,6) CHECK (latitud  BETWEEN -90  AND 90),
    longitud              NUMERIC(9,6) CHECK (longitud BETWEEN -180 AND 180),
    CONSTRAINT uq_punto_interes UNIQUE (localidad_id, nombre)
);

-- N:M hotel - punto de interés; la distancia es atributo de la relación
CREATE TABLE hotel_punto_interes (
    hotel_id         INTEGER NOT NULL REFERENCES hotel(hotel_id) ON DELETE CASCADE,
    punto_interes_id INTEGER NOT NULL REFERENCES punto_interes(punto_interes_id),
    distancia_m      INTEGER NOT NULL CHECK (distancia_m >= 0),
    PRIMARY KEY (hotel_id, punto_interes_id)
);

-- ---------------------------------------------------------------------
-- 3. Habitaciones, tipos, comodidades y tarifas de lista
-- ---------------------------------------------------------------------
CREATE TABLE tipo_habitacion (
    tipo_habitacion_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre             VARCHAR(50) NOT NULL UNIQUE,   -- Single, Doble, Suite...
    capacidad_maxima   SMALLINT    NOT NULL CHECK (capacidad_maxima BETWEEN 1 AND 12),
    descripcion        TEXT
);

CREATE TABLE comodidad (
    comodidad_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre       VARCHAR(60) NOT NULL UNIQUE           -- Wi-Fi, Aire acondicionado...
);

CREATE TABLE habitacion (
    habitacion_id      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hotel_id           INTEGER     NOT NULL REFERENCES hotel(hotel_id),
    tipo_habitacion_id SMALLINT    NOT NULL REFERENCES tipo_habitacion(tipo_habitacion_id),
    numero             VARCHAR(10) NOT NULL,           -- "101", "PB-3"
    piso               SMALLINT    NOT NULL CHECK (piso BETWEEN -5 AND 200),
    activa             BOOLEAN     NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_habitacion_numero UNIQUE (hotel_id, numero)
);

-- Las comodidades se asignan por habitación (dos dobles del mismo hotel
-- pueden diferir: una con balcón y otra sin)
CREATE TABLE habitacion_comodidad (
    habitacion_id INTEGER  NOT NULL REFERENCES habitacion(habitacion_id) ON DELETE CASCADE,
    comodidad_id  SMALLINT NOT NULL REFERENCES comodidad(comodidad_id),
    PRIMARY KEY (habitacion_id, comodidad_id)
);

-- Tarifa de lista por hotel y tipo de habitación, con vigencia.
-- Es la referencia comercial; la tarifa pactada queda en la reserva.
CREATE TABLE tarifa (
    tarifa_id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hotel_id           INTEGER       NOT NULL REFERENCES hotel(hotel_id),
    tipo_habitacion_id SMALLINT      NOT NULL REFERENCES tipo_habitacion(tipo_habitacion_id),
    vigencia_desde     DATE          NOT NULL,
    vigencia_hasta     DATE,                           -- NULL = vigente sin fin
    precio_noche       NUMERIC(12,2) NOT NULL CHECK (precio_noche > 0),
    CONSTRAINT ck_tarifa_vigencia CHECK (vigencia_hasta IS NULL OR vigencia_hasta > vigencia_desde),
    -- dos tarifas del mismo hotel/tipo no pueden tener vigencias solapadas
    CONSTRAINT ex_tarifa_solapada EXCLUDE USING gist (
        hotel_id WITH =,
        tipo_habitacion_id WITH =,
        daterange(vigencia_desde, vigencia_hasta, '[)') WITH &&
    )
);

-- ---------------------------------------------------------------------
-- 4. Huéspedes y sus medios de contacto
-- ---------------------------------------------------------------------
CREATE TABLE huesped (
    huesped_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_documento   VARCHAR(10)  NOT NULL CHECK (tipo_documento IN ('DNI','PASAPORTE','CI','LE','LC','OTRO')),
    numero_documento VARCHAR(20)  NOT NULL,
    nombre           VARCHAR(80)  NOT NULL,
    apellido         VARCHAR(80)  NOT NULL,
    fecha_nacimiento DATE         CHECK (fecha_nacimiento > DATE '1900-01-01'),
    nacionalidad_id  SMALLINT     REFERENCES pais(pais_id),
    domicilio_id     BIGINT       UNIQUE REFERENCES domicilio(domicilio_id),
    fecha_registro   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_huesped_documento UNIQUE (tipo_documento, numero_documento)
);

CREATE TABLE huesped_telefono (
    huesped_telefono_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    huesped_id BIGINT      NOT NULL REFERENCES huesped(huesped_id) ON DELETE CASCADE,
    tipo       VARCHAR(10) NOT NULL DEFAULT 'MOVIL' CHECK (tipo IN ('MOVIL','FIJO','TRABAJO')),
    numero     VARCHAR(25) NOT NULL CHECK (numero ~ '^\+?[0-9 ()-]{6,24}$'),
    principal  BOOLEAN     NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_huesped_telefono UNIQUE (huesped_id, numero)
);
CREATE UNIQUE INDEX uq_huesped_telefono_principal
    ON huesped_telefono (huesped_id) WHERE principal;

CREATE TABLE huesped_email (
    huesped_email_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    huesped_id BIGINT       NOT NULL REFERENCES huesped(huesped_id) ON DELETE CASCADE,
    email      VARCHAR(254) NOT NULL CHECK (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    principal  BOOLEAN      NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_huesped_email UNIQUE (huesped_id, email)
);
CREATE UNIQUE INDEX uq_huesped_email_principal
    ON huesped_email (huesped_id) WHERE principal;

-- ---------------------------------------------------------------------
-- 5. Reservas
-- ---------------------------------------------------------------------
-- Estados: P=Pendiente, C=Confirmada, F=Finalizada (check-out),
--          X=Cancelada, N=No-show
CREATE TABLE estado_reserva (
    estado      CHAR(1)     PRIMARY KEY CHECK (estado IN ('P','C','F','X','N')),
    descripcion VARCHAR(30) NOT NULL UNIQUE,
    ocupa       BOOLEAN     NOT NULL      -- ¿bloquea la habitación?
);

CREATE TABLE reserva (
    reserva_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    habitacion_id      INTEGER       NOT NULL REFERENCES habitacion(habitacion_id),
    huesped_id         BIGINT        NOT NULL REFERENCES huesped(huesped_id),
    fecha_inicio       DATE          NOT NULL,   -- noche de llegada
    fecha_fin          DATE          NOT NULL,   -- día de salida (no se cobra)
    cantidad_huespedes SMALLINT      NOT NULL DEFAULT 1 CHECK (cantidad_huespedes BETWEEN 1 AND 12),
    estado             CHAR(1)       NOT NULL DEFAULT 'P' REFERENCES estado_reserva(estado),
    tarifa_noche       NUMERIC(12,2) CHECK (tarifa_noche > 0),
    fecha_creacion     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    fecha_confirmacion TIMESTAMPTZ,
    observaciones      TEXT,

    CONSTRAINT ck_reserva_fechas CHECK (fecha_fin > fecha_inicio),
    CONSTRAINT ck_reserva_duracion CHECK (fecha_fin - fecha_inicio <= 90),
    -- La tarifa existe sólo si la reserva fue confirmada (C o F).
    -- Pendientes: sin tarifa. Canceladas / no-show: conservan la que tenían.
    CONSTRAINT ck_reserva_tarifa CHECK (
           (estado = 'P'        AND tarifa_noche IS NULL     AND fecha_confirmacion IS NULL)
        OR (estado IN ('C','F') AND tarifa_noche IS NOT NULL AND fecha_confirmacion IS NOT NULL)
        OR (estado IN ('X','N'))
    ),
    -- Regla central: una habitación no puede tener dos reservas activas
    -- con períodos superpuestos. Intervalo [inicio, fin): el día de salida
    -- de una reserva puede ser el de llegada de la siguiente.
    CONSTRAINT ex_reserva_superpuesta EXCLUDE USING gist (
        habitacion_id WITH =,
        daterange(fecha_inicio, fecha_fin, '[)') WITH &&
    ) WHERE (estado IN ('P','C','F'))
);

-- ---------------------------------------------------------------------
-- 6. Regla que cruza tablas: la cantidad de huéspedes no puede superar
--    la capacidad del tipo de habitación (no expresable con CHECK).
-- ---------------------------------------------------------------------
CREATE FUNCTION fn_valida_capacidad() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_cap SMALLINT;
BEGIN
    SELECT th.capacidad_maxima INTO v_cap
      FROM habitacion h
      JOIN tipo_habitacion th USING (tipo_habitacion_id)
     WHERE h.habitacion_id = NEW.habitacion_id;

    IF NEW.cantidad_huespedes > v_cap THEN
        RAISE EXCEPTION 'La habitación % admite como máximo % huéspedes (se pidieron %)',
              NEW.habitacion_id, v_cap, NEW.cantidad_huespedes
              USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_reserva_capacidad
    BEFORE INSERT OR UPDATE OF habitacion_id, cantidad_huespedes ON reserva
    FOR EACH ROW EXECUTE FUNCTION fn_valida_capacidad();

-- ---------------------------------------------------------------------
-- 7. Índices sobre claves foráneas (PostgreSQL NO los crea solo).
--    La estrategia completa de índices se desarrolla en la Parte III.
-- ---------------------------------------------------------------------
CREATE INDEX ix_provincia_pais          ON provincia (pais_id);
CREATE INDEX ix_domicilio_localidad     ON domicilio (localidad_id);
CREATE INDEX ix_hotel_contacto_tipo     ON hotel_contacto (tipo_contacto_id);
CREATE INDEX ix_punto_interes_localidad ON punto_interes (localidad_id);
CREATE INDEX ix_hpi_punto               ON hotel_punto_interes (punto_interes_id);
CREATE INDEX ix_habitacion_tipo         ON habitacion (tipo_habitacion_id);
CREATE INDEX ix_hab_comodidad_comodidad ON habitacion_comodidad (comodidad_id);
CREATE INDEX ix_huesped_telefono_h      ON huesped_telefono (huesped_id);
CREATE INDEX ix_huesped_email_h         ON huesped_email (huesped_id);
CREATE INDEX ix_reserva_huesped         ON reserva (huesped_id);
-- reserva.habitacion_id ya queda cubierta por el índice GiST de la
-- restricción EXCLUDE; habitacion.hotel_id por uq_habitacion_numero.

-- ---------------------------------------------------------------------
-- 8. Catálogos fijos
-- ---------------------------------------------------------------------
INSERT INTO estado_reserva VALUES
    ('P','Pendiente',  TRUE),
    ('C','Confirmada', TRUE),
    ('F','Finalizada', TRUE),
    ('X','Cancelada',  FALSE),
    ('N','No-show',    FALSE);

INSERT INTO tipo_contacto (nombre) VALUES
    ('TELEFONO'),('EMAIL'),('WEB'),('WHATSAPP');
