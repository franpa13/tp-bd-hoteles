-- =====================================================================
-- Script 05 (se aplica en la Parte VII, con la base cargada): desnormalización controlada
-- Protegida por FK compuesta (habitacion_id, hotel_id) → habitacion.
-- =====================================================================
SET search_path TO hotel, public;

ALTER TABLE habitacion ADD CONSTRAINT uq_habitacion_hotel UNIQUE (habitacion_id, hotel_id);
ALTER TABLE reserva ADD COLUMN hotel_id INTEGER;
UPDATE reserva r SET hotel_id = h.hotel_id
  FROM habitacion h WHERE h.habitacion_id = r.habitacion_id;
ALTER TABLE reserva ALTER COLUMN hotel_id SET NOT NULL,
  ADD CONSTRAINT fk_reserva_hab_hotel FOREIGN KEY (habitacion_id, hotel_id)
      REFERENCES habitacion (habitacion_id, hotel_id) ON UPDATE CASCADE;
CREATE INDEX ix_reserva_hotel_fecha ON reserva (hotel_id, fecha_inicio);
ANALYZE reserva;
