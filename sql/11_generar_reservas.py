#!/usr/bin/env python3
"""
Script 11: generador reproducible de reservas.

Para cada habitación recorre el calendario desde FECHA_DESDE hasta
FECHA_HASTA alternando estadías y días libres, de modo que nunca genera
dos reservas activas superpuestas en la misma habitación (las canceladas
y no-show se intercalan sin ocupar).

Distribución (criterios documentados en el informe, Punto 19):
  - Estadía: 1 a 14 noches, moda en 2 noches.
  - Días libres entre estadías: menos en temporada alta (ene, feb, jul),
    más en temporada baja; cada hotel tiene un factor de popularidad.
  - Huésped: sesgado (pocos huéspedes frecuentes concentran muchas reservas).
  - Estado según la fecha respecto de HOY: pasadas -> F/X/N, futuras -> C/P/X.
  - Tarifa por noche en USD: categoría x tipo x temporada x año.
Salida: CSV ordenado por fecha_creacion (orden real de inserción).

Uso: python3 11_generar_reservas.py salida.csv
"""
import csv, os, random, sys, datetime as dt
import psycopg

SEED = 42
FECHA_DESDE = dt.date(2015, 1, 1)
FECHA_HASTA = dt.date(2027, 6, 30)
HOY = dt.date(2026, 10, 11)          # fecha fija: el TP es reproducible
DSN = (f"host={os.getenv('PGHOST', 'localhost')} port={os.getenv('PGPORT', '5432')} "
       f"user={os.getenv('PGUSER', 'postgres')} password={os.getenv('PGPASSWORD', 'postgres')} "
       f"dbname={os.getenv('PGDATABASE', 'hoteles')} options=-csearch_path=hotel")

rnd = random.Random(SEED)
ESTADIA = [1]*20 + [2]*25 + [3]*20 + [4]*12 + [5]*8 + [6]*5 + [7]*5 + [10]*3 + [14]*2
TEMPORADA = {1: 'alta', 2: 'alta', 7: 'alta', 3: 'media', 10: 'media', 12: 'media'}
GAP_MEDIO = {'alta': 0.7, 'media': 2.0, 'baja': 3.2}
FACTOR_TEMP = {'alta': 1.30, 'media': 1.10, 'baja': 1.00}
BASE_CAT = {1: 35, 2: 50, 3: 80, 4: 130, 5: 220}
FACTOR_TIPO = {1: 0.8, 2: 1.0, 3: 1.25, 4: 1.45, 5: 2.2, 6: 1.7}
OBS = ['Llegada tarde', 'Solicita cuna', 'Cama extra', 'Aniversario', 'Piso alto',
       'Celíaco', 'Traslado desde aeropuerto', 'Mascota pequeña']

with psycopg.connect(DSN) as con:
    habs = con.execute("""
        SELECT hb.habitacion_id, hb.tipo_habitacion_id, th.capacidad_maxima, h.hotel_id, h.categoria
          FROM habitacion hb JOIN tipo_habitacion th USING (tipo_habitacion_id)
          JOIN hotel h USING (hotel_id) ORDER BY hb.habitacion_id""").fetchall()
    n_huespedes = con.execute("SELECT max(huesped_id) FROM huesped").fetchone()[0]

popularidad = {}
for _, _, _, hotel_id, _ in habs:
    if hotel_id not in popularidad:
        popularidad[hotel_id] = rnd.uniform(0.55, 1.6)

def huesped():
    # potencia > 1 concentra la elección en los ids bajos: huéspedes frecuentes
    return 1 + int(n_huespedes * rnd.random() ** 2.2)

def temporada(d):
    return TEMPORADA.get(d.month, 'baja')

out = open(sys.argv[1], 'w', newline='')
w = csv.writer(out)
total = 0
for hab_id, tipo, cap, hotel_id, cat in habs:
    d = FECHA_DESDE + dt.timedelta(days=rnd.randint(0, 5))
    pop = popularidad[hotel_id]
    while True:
        noches = rnd.choice(ESTADIA)
        fin = d + dt.timedelta(days=noches)
        if fin > FECHA_HASTA:
            break
        temp = temporada(d)
        anticipacion = int(rnd.random() ** 2 * 120)            # muchas reservas de último momento
        creacion = dt.datetime.combine(d, dt.time()) - dt.timedelta(
            days=anticipacion, minutes=rnd.randint(0, 1439))
        r = rnd.random()
        if d < HOY:
            estado = 'F' if r < 0.86 else ('X' if r < 0.96 else 'N')
        else:
            estado = 'C' if r < 0.55 else ('P' if r < 0.90 else 'X')
        confirmada = estado in ('C', 'F') or (estado in ('X', 'N') and rnd.random() < 0.5)
        if confirmada:
            tarifa = round(BASE_CAT[cat] * FACTOR_TIPO[tipo] * FACTOR_TEMP[temp]
                           * (1 + 0.03 * (d.year - 2015)) * rnd.uniform(0.9, 1.1), 2)
            conf = creacion + dt.timedelta(minutes=rnd.randint(5, 2880))
            if conf.date() > d:
                conf = creacion + dt.timedelta(minutes=5)
            conf_s = conf.isoformat(sep=' ') + '-03'
        else:
            tarifa, conf_s = '', ''
        personas = max(1, cap - (rnd.random() < 0.4) * rnd.randint(0, cap - 1))
        obs = rnd.choice(OBS) if rnd.random() < 0.05 else ''
        w.writerow([creacion.isoformat(sep=' ') + '-03', hab_id, huesped(), d.isoformat(),
                    fin.isoformat(), personas, estado, tarifa, conf_s, obs])
        total += 1
        # las canceladas / no-show no ocupan: la próxima puede empezar el mismo día
        if estado in ('X', 'N') and rnd.random() < 0.5:
            continue
        gap = rnd.expovariate(1 / (GAP_MEDIO[temp] / pop))
        d = fin + dt.timedelta(days=int(gap))
out.close()
print(f"habitaciones={len(habs)} reservas={total}")
