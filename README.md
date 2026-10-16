# TP Diseño y Optimización de Bases de Datos — Cadena de Hoteles

Informe completo: [`TP_BD_Cadena_Hoteles.pdf`](TP_BD_Cadena_Hoteles.pdf) (puntos 1 a 52).

Motor: **PostgreSQL 16**. Todas las tablas viven en el esquema `hotel`.

## Estructura

```
├── docker-compose.yml        PostgreSQL 16 listo para usar
├── sql/                      scripts numerados por orden de ejecución
├── resultados/               salida original de cada experimento (de donde salen las cifras del informe)
└── TP_BD_Cadena_Hoteles.pdf  informe
```

> Las mediciones del informe se tomaron con PostgreSQL 16 instalado de forma nativa sobre una VM Linux
> (Ubuntu 24.04, 2 núcleos, 7,8 GB de RAM), sin contenedores. Con Docker los tiempos absolutos cambian;
> las proporciones entre variantes y las páginas leídas deberían mantenerse.

## Requisitos

- Docker y Docker Compose
- Python 3.10+
- Cliente `psql` (para la carga masiva con `\copy`). En Ubuntu: `sudo apt install postgresql-client`

## Puesta en marcha

```bash
git clone <url-del-repo> && cd tp-bd-hoteles
docker compose up -d                      # levanta PostgreSQL 16 en localhost:5433
cp .env.example .env && set -a && source .env && set +a   # variables de conexión
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Para ejecutar un script SQL dentro del contenedor:

```bash
docker compose exec db psql -U postgres -d hoteles -f /sql/01_schema.sql
```

## Orden de ejecución

| # | Comando | Puntos |
|---|---|---|
| 1 | `docker compose exec db psql -U postgres -d hoteles -f /sql/01_schema.sql` | 2, 4, 6, 8 |
| 2 | `docker compose exec db psql -U postgres -d hoteles -f /sql/02_pruebas_integridad.sql` | 4 (14 pruebas de reglas de negocio) |
| 3 | `docker compose exec db psql -U postgres -d hoteles -f /sql/03_tipos_datos.sql` | 7 |
| 4 | `docker compose exec db psql -U postgres -d hoteles -f /sql/04_impacto_restricciones.sql` | 8 |
| 5 | `docker compose exec db psql -U postgres -d hoteles -f /sql/01_schema.sql` | base limpia para la carga |
| 6 | `docker compose exec db psql -U postgres -d hoteles -f /sql/10_generar_base.sql` | 19 (1 M de huéspedes, ~1 min) |
| 7 | `cd sql && python3 11_generar_reservas.py ../reservas_raw.csv` | 19 (7,5 M reservas, ~2 min) |
| 8 | `LC_ALL=C sort -t, -k1,1 ../reservas_raw.csv > ../reservas.csv` | 19 |
| 9 | `./12_carga_masiva.sh ../reservas.csv` | 20 (~8 min) |
| 10 | `docker compose exec db psql -U postgres -d hoteles -f /sql/22_distribucion.sql` | 21 |
| 11 | `python3 20_indices.py` | 12–18 |
| 12 | `docker compose exec db psql -U postgres -d hoteles -f /sql/21_estrategia_indices.sql` | 11 |
| 13 | `python3 31_correr_consultas.py` (consultas en `30_consultas.sql`) | 24–27 |
| 14 | `python3 32_transporte.py` | 28 |
| 15 | `python3 40_optimizador.py` y `python3 41_estadisticas_extra.py` | 29–33 |
| 16 | `python3 50_optimizacion.py` y `python3 52_optimizacion_resto.py` | 34–37 |
| 17 | `docker compose exec db psql -U postgres -d hoteles -f /sql/53_mantenimiento_reserva.sql` y `python3 51_seguimiento_cobertura.py` | 37, 48 |
| 18 | `python3 60_concurrencia.py` | 38–42 |
| 19 | `python3 80_particiones.py` y `python3 81_particiones_extra.py` | 50–52 |

Los pasos 7 a 19 se corren desde la carpeta `sql/` con las variables del `.env` cargadas.

### Scripts que necesitan instalación nativa

`70_servidor.py` y `71_servidor_resto.py` (Puntos 23 y 43–48) **reinician el servidor con `pg_ctl` y vacían la
caché del sistema operativo**, por eso requieren PostgreSQL instalado en la máquina y permisos de root.
Con Docker, el equivalente manual es:

```bash
docker compose restart db                         # vacía shared_buffers (caché fría de PostgreSQL)
sync && echo 3 | sudo tee /proc/sys/vm/drop_caches  # vacía la caché del SO (Linux)
```

## Reproducibilidad

Los datos se generan con semillas fijas (`setseed(0.42)` y `random.Random(42)`) y una fecha "hoy" fija
(11/10/2026): dos ejecuciones producen exactamente los mismos datos.
