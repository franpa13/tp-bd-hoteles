#!/usr/bin/env python3
"""Script 41: Punto 31 (complemento) — estadísticas multicolumna y plan que cambia con estadísticas viejas."""
from tp import *

c = conectar()
titulo("PUNTO 31b — Columnas correlacionadas por igualdad: tipo_documento y nacionalidad")
print("conteo real:", c.execute("SELECT tipo_documento, nacionalidad_id = 1 AS argentino, count(*) FROM huesped GROUP BY 1, 2 ORDER BY 1, 2").fetchall())
q = "SELECT count(*) FROM huesped WHERE tipo_documento = 'PASAPORTE' AND nacionalidad_id = 1"
print("--- Sin estadísticas multicolumna\n" + plan(c, q))
c.execute("CREATE STATISTICS st_doc_nac (dependencies, mcv) ON tipo_documento, nacionalidad_id FROM huesped")
c.execute("ANALYZE huesped")
print("--- Con CREATE STATISTICS (dependencies, mcv) ON tipo_documento, nacionalidad_id\n" + plan(c, q))
print("dependencias medidas:", c.execute("SELECT dependencies FROM pg_stats_ext WHERE statistics_name = 'st_doc_nac'").fetchone())
c.execute("DROP STATISTICS st_doc_nac")
c.execute("ANALYZE huesped")

titulo("PUNTO 31c — Estadísticas viejas que cambian el método de JOIN")
c.execute("DROP TABLE IF EXISTS r_stats")
c.execute("CREATE TABLE r_stats WITH (autovacuum_enabled = off) AS SELECT * FROM reserva WHERE fecha_inicio < '2016-01-01'")
c.execute("CREATE INDEX ON r_stats (fecha_inicio)")
c.execute("ANALYZE r_stats")
c.execute("""INSERT INTO r_stats SELECT reserva_id, habitacion_id, huesped_id, fecha_inicio + 5479, fecha_fin + 5479,
             cantidad_huespedes, estado, tarifa_noche, fecha_creacion, fecha_confirmacion, observaciones
             FROM reserva WHERE fecha_inicio < '2016-01-01'""")
q = """SELECT hu.apellido, count(*) FROM r_stats r JOIN huesped hu ON hu.huesped_id = r.huesped_id
        WHERE r.fecha_inicio >= '2030-01-01' GROUP BY hu.apellido"""
medir(c, "Antes de ANALYZE (el optimizador cree que no hay filas de 2030)", q, reps=3)
c.execute("ANALYZE r_stats")
medir(c, "Después de ANALYZE", q, reps=3)
c.execute("DROP TABLE r_stats")
print("FIN")
