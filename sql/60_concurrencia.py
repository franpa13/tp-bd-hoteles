#!/usr/bin/env python3
"""
Script 60: Parte VIII — bloqueos, concurrencia, aislamiento y deadlocks (Puntos 38 a 42).
Usa dos conexiones (A y B) y una tercera (M) que observa pg_locks / pg_stat_activity
mientras B espera. Todos los cambios se revierten al final.
"""
import threading, time
import psycopg
from tp import DSN, titulo

def con(nombre):
    c = psycopg.connect(DSN + f" application_name={nombre}", autocommit=True)
    return c

M = con("monitor")
M.execute("SET search_path TO hotel")
R1, R2 = 1000, 2000          # reservas usadas en las pruebas
T0 = time.perf_counter()

def t():
    return f"{time.perf_counter()-T0:6.2f}s"

def log(quien, msg):
    print(f"[{t()}] {quien}: {msg}", flush=True)

def en_hilo(fn):
    h = threading.Thread(target=fn); h.start(); return h

def esperando():
    """Qué está esperando cada sesión y quién la bloquea (Punto 42)."""
    filas = M.execute("""
        SELECT a.application_name, a.wait_event_type, a.wait_event, pg_blocking_pids(a.pid) AS bloqueado_por,
               left(a.query, 60)
          FROM pg_stat_activity a
         WHERE a.application_name IN ('A','B') AND a.state <> 'idle'""").fetchall()
    for f in filas:
        print("        pg_stat_activity:", f)
    locks = M.execute("""
        SELECT a.application_name, l.locktype, coalesce(l.relation::regclass::text, ''), l.mode, l.granted
          FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid
         WHERE a.application_name IN ('A','B') AND (l.locktype IN ('relation','tuple','transactionid'))
           AND (l.relation IS NULL OR l.relation = 'hotel.reserva'::regclass)
         ORDER BY 1, l.granted DESC""").fetchall()
    for f in locks:
        print("        pg_locks:", f)

def ejecutar_b(sql, resultado):
    def f():
        try:
            log("B", f"ejecuta  {sql[:70]}")
            r = B.execute(sql)
            filas = r.fetchall() if r.description else None
            resultado.append(("ok", filas))
            log("B", f"terminó  -> {filas}")
        except Exception as e:
            resultado.append(("error", str(e).split("\n")[0]))
            log("B", f"ERROR    -> {str(e).splitlines()[0]}")
    return en_hilo(f)

A = con("A"); B = con("B")
for x in (A, B):
    x.execute("SET search_path TO hotel")
    x.execute("SET lock_timeout = '15s'")

# ======================================================================
titulo("PUNTO 38 — Bloqueos de tabla y de fila")
print("\n>> 38.1 LOCK TABLE ... IN ACCESS EXCLUSIVE MODE bloquea hasta las lecturas")
A.execute("BEGIN"); A.execute("LOCK TABLE reserva IN ACCESS EXCLUSIVE MODE"); log("A", "LOCK TABLE reserva IN ACCESS EXCLUSIVE MODE")
res = []; h = ejecutar_b(f"SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1}", res)
time.sleep(1.5); esperando()
A.execute("COMMIT"); log("A", "COMMIT"); h.join()

print("\n>> 38.2 LOCK TABLE ... IN SHARE MODE: deja leer, bloquea escribir")
A.execute("BEGIN"); A.execute("LOCK TABLE reserva IN SHARE MODE"); log("A", "LOCK TABLE reserva IN SHARE MODE")
res = []; h = ejecutar_b(f"SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1}", res); h.join()
res = []; h = ejecutar_b(f"UPDATE reserva SET observaciones = 'B' WHERE reserva_id = {R1}", res)
time.sleep(1.5); esperando()
A.execute("COMMIT"); log("A", "COMMIT"); h.join()
A.execute(f"UPDATE reserva SET observaciones = NULL WHERE reserva_id = {R1}")

print("\n>> 38.3 Bloqueo compartido de fila (FOR SHARE): otro FOR SHARE convive, UPDATE espera")
A.execute("BEGIN"); A.execute(f"SELECT * FROM reserva WHERE reserva_id = {R1} FOR SHARE"); log("A", f"SELECT ... FOR SHARE (reserva {R1})")
B.execute("BEGIN")
res = []; h = ejecutar_b(f"SELECT reserva_id FROM reserva WHERE reserva_id = {R1} FOR SHARE", res); h.join()
B.execute("COMMIT")
res = []; h = ejecutar_b(f"UPDATE reserva SET observaciones = 'B' WHERE reserva_id = {R1}", res)
time.sleep(1.5); esperando()
A.execute("ROLLBACK"); log("A", "ROLLBACK"); h.join()
A.execute(f"UPDATE reserva SET observaciones = NULL WHERE reserva_id = {R1}")

print("\n>> 38.4 Bloqueo exclusivo de fila (FOR UPDATE): una lectura simple NO espera (MVCC), otro FOR UPDATE sí")
A.execute("BEGIN"); A.execute(f"SELECT * FROM reserva WHERE reserva_id = {R1} FOR UPDATE"); log("A", f"SELECT ... FOR UPDATE (reserva {R1})")
res = []; h = ejecutar_b(f"SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1}", res); h.join()
res = []; h = ejecutar_b(f"SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1} FOR UPDATE NOWAIT", res); h.join()
res = []; h = ejecutar_b(f"SELECT reserva_id FROM reserva WHERE reserva_id IN ({R1},{R2}) FOR UPDATE SKIP LOCKED", res); h.join()
A.execute("ROLLBACK"); log("A", "ROLLBACK")

# ======================================================================
titulo("PUNTO 39 — Dos conexiones modificando y leyendo el mismo registro")
orig = M.execute(f"SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1}").fetchone()[0]
print(f"tarifa original de la reserva {R1}: {orig}")
A.execute("BEGIN"); A.execute(f"UPDATE reserva SET tarifa_noche = tarifa_noche + 100 WHERE reserva_id = {R1}"); log("A", "UPDATE tarifa +100 (sin COMMIT)")
res = []; h = ejecutar_b(f"SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1}", res); h.join()
res = []; h = ejecutar_b(f"UPDATE reserva SET tarifa_noche = tarifa_noche + 1 WHERE reserva_id = {R1} RETURNING tarifa_noche", res)
time.sleep(2); esperando()
A.execute("COMMIT"); log("A", "COMMIT"); h.join()
log("M", f"valor final: {M.execute(f'SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1}').fetchone()[0]} (B aplicó su +1 sobre el valor confirmado por A: no hay actualización perdida)")
M.execute(f"UPDATE reserva SET tarifa_noche = {orig} WHERE reserva_id = {R1}")

print("\n>> 39.2 Carrera por la misma habitación: dos reservas superpuestas simultáneas")
hab = M.execute("SELECT habitacion_id FROM habitacion WHERE hotel_id = 13 LIMIT 1").fetchone()[0]
hotelcol = M.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='reserva' AND column_name='hotel_id'").fetchone()[0]
cols = "(habitacion_id, huesped_id, fecha_inicio, fecha_fin" + (", hotel_id)" if hotelcol else ")")
vals = lambda h_, hu: f"({h_}, {hu}, '2029-03-10', '2029-03-15'" + (", 13)" if hotelcol else ")")
A.execute("BEGIN"); A.execute(f"INSERT INTO reserva {cols} VALUES {vals(hab, 11)}"); log("A", f"INSERT habitación {hab} del 10 al 15/03/2029 (sin COMMIT)")
res = []; h = ejecutar_b(f"INSERT INTO reserva {cols} VALUES {vals(hab, 22)}", res)
time.sleep(2); esperando()
A.execute("COMMIT"); log("A", "COMMIT"); h.join()
print("   -> repetimos, pero A hace ROLLBACK:")
M.execute(f"DELETE FROM reserva WHERE habitacion_id = {hab} AND fecha_inicio = '2029-03-10'")
A.execute("BEGIN"); A.execute(f"INSERT INTO reserva {cols} VALUES {vals(hab, 11)}"); log("A", "INSERT (sin COMMIT)")
res = []; h = ejecutar_b(f"INSERT INTO reserva {cols} VALUES {vals(hab, 22)}", res)
time.sleep(1.5)
A.execute("ROLLBACK"); log("A", "ROLLBACK"); h.join()
M.execute(f"DELETE FROM reserva WHERE habitacion_id = {hab} AND fecha_inicio = '2029-03-10'")

# ======================================================================
titulo("PUNTO 40 — Niveles de aislamiento")
def nivel(n):
    B.execute(f"BEGIN ISOLATION LEVEL {n}")

print("\n>> 40.1 Dirty read con READ UNCOMMITTED")
A.execute("BEGIN"); A.execute(f"UPDATE reserva SET tarifa_noche = 1 WHERE reserva_id = {R1}"); log("A", "UPDATE tarifa = 1 (sin COMMIT)")
nivel("READ UNCOMMITTED")
log("B", f"lee: {B.execute(f'SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1}').fetchone()[0]}  (no ve el 1: PostgreSQL trata READ UNCOMMITTED como READ COMMITTED)")
B.execute("COMMIT"); A.execute("ROLLBACK")

for niv in ("READ COMMITTED", "REPEATABLE READ"):
    print(f"\n>> 40.2 Non-repeatable read con {niv}")
    nivel(niv)
    v1 = B.execute(f"SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1}").fetchone()[0]; log("B", f"1ª lectura: {v1}")
    A.execute(f"UPDATE reserva SET tarifa_noche = tarifa_noche + 50 WHERE reserva_id = {R1}"); log("A", "UPDATE +50 y COMMIT (autocommit)")
    v2 = B.execute(f"SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1}").fetchone()[0]; log("B", f"2ª lectura: {v2}  -> {'CAMBIÓ (non-repeatable read)' if v1 != v2 else 'igual'}")
    B.execute("COMMIT"); M.execute(f"UPDATE reserva SET tarifa_noche = {orig} WHERE reserva_id = {R1}")

for niv in ("READ COMMITTED", "REPEATABLE READ"):
    print(f"\n>> 40.3 Phantom read con {niv}")
    nivel(niv)
    q = f"SELECT count(*) FROM reserva WHERE habitacion_id = {hab} AND fecha_inicio >= '2029-01-01'"
    n1 = B.execute(q).fetchone()[0]; log("B", f"cuenta reservas 2029 de la habitación: {n1}")
    A.execute(f"INSERT INTO reserva {cols} VALUES {vals(hab, 33)}"); log("A", "INSERT nueva reserva 2029 y COMMIT")
    n2 = B.execute(q).fetchone()[0]; log("B", f"vuelve a contar: {n2}  -> {'APARECIÓ UN FANTASMA' if n2 != n1 else 'igual'}")
    B.execute("COMMIT"); M.execute(f"DELETE FROM reserva WHERE habitacion_id = {hab} AND fecha_inicio = '2029-03-10'")

print("\n>> 40.4 REPEATABLE READ: actualización concurrente de la misma fila")
nivel("REPEATABLE READ"); B.execute(f"SELECT tarifa_noche FROM reserva WHERE reserva_id = {R1}").fetchone()
A.execute(f"UPDATE reserva SET tarifa_noche = tarifa_noche + 5 WHERE reserva_id = {R1}"); log("A", "UPDATE +5 y COMMIT")
try:
    B.execute(f"UPDATE reserva SET tarifa_noche = tarifa_noche + 7 WHERE reserva_id = {R1}"); log("B", "UPDATE ok")
except Exception as e:
    log("B", f"ERROR -> {str(e).splitlines()[0]}")
B.execute("ROLLBACK"); M.execute(f"UPDATE reserva SET tarifa_noche = {orig} WHERE reserva_id = {R1}")

print("\n>> 40.5 Write skew: regla 'un huésped no puede tener dos reservas pendientes que empiecen el mismo día'")
habs2 = [r[0] for r in M.execute("SELECT habitacion_id FROM habitacion WHERE hotel_id = 13 ORDER BY habitacion_id LIMIT 3 OFFSET 1").fetchall()]
def intento(c_, h_, quien):
    n = c_.execute("SELECT count(*) FROM reserva WHERE huesped_id = 999999 AND estado = 'P' AND fecha_inicio = '2029-05-01'").fetchone()[0]
    log(quien, f"verifica: {n} pendientes -> inserta")
    c_.execute(f"INSERT INTO reserva {cols.replace('fecha_fin', 'fecha_fin')} VALUES ({h_}, 999999, '2029-05-01', '2029-05-03'" + (", 13)" if hotelcol else ")"))
for niv in ("REPEATABLE READ", "SERIALIZABLE"):
    print(f"   -- {niv}")
    A.execute(f"BEGIN ISOLATION LEVEL {niv}"); B.execute(f"BEGIN ISOLATION LEVEL {niv}")
    intento(A, habs2[0], "A"); intento(B, habs2[1], "B")
    for quien, c_ in (("A", A), ("B", B)):
        try:
            c_.execute("COMMIT"); log(quien, "COMMIT ok")
        except Exception as e:
            log(quien, f"COMMIT ERROR -> {str(e).splitlines()[0]}"); c_.execute("ROLLBACK")
    n = M.execute("SELECT count(*) FROM reserva WHERE huesped_id = 999999 AND fecha_inicio = '2029-05-01'").fetchone()[0]
    log("M", f"reservas pendientes del huésped ese día: {n} {'(regla violada)' if n > 1 else '(regla respetada)'}")
    M.execute("DELETE FROM reserva WHERE huesped_id = 999999 AND fecha_inicio = '2029-05-01'")

# ======================================================================
titulo("PUNTO 41 — Deadlock")
print("deadlock_timeout =", M.execute("SHOW deadlock_timeout").fetchone()[0])
dl0 = M.execute("SELECT deadlocks FROM pg_stat_database WHERE datname='hoteles'").fetchone()[0]
A.execute("BEGIN"); B.execute("BEGIN")
A.execute(f"UPDATE reserva SET observaciones = 'A' WHERE reserva_id = {R1}"); log("A", f"bloquea reserva {R1}")
B.execute(f"UPDATE reserva SET observaciones = 'B' WHERE reserva_id = {R2}"); log("B", f"bloquea reserva {R2}")
resA = []
def a_pide():
    try:
        log("A", f"pide reserva {R2}...")
        A.execute(f"UPDATE reserva SET observaciones = 'A' WHERE reserva_id = {R2}"); resA.append("ok"); log("A", f"obtuvo {R2}")
    except Exception as e:
        resA.append(str(e)); log("A", f"ERROR -> {str(e).splitlines()[0]}")
ha = en_hilo(a_pide); time.sleep(0.5); esperando()
try:
    log("B", f"pide reserva {R1}... (ciclo: A espera a B y B espera a A)")
    B.execute(f"UPDATE reserva SET observaciones = 'B' WHERE reserva_id = {R1}"); log("B", "obtuvo")
except Exception as e:
    log("B", "ERROR -> " + " | ".join(str(e).splitlines()[:3]))
ha.join()
for c_ in (A, B):
    try: c_.execute("ROLLBACK")
    except Exception: pass
dl1 = M.execute("SELECT deadlocks FROM pg_stat_database WHERE datname='hoteles'").fetchone()[0]
print(f"pg_stat_database.deadlocks: {dl0} -> {dl1}")

print("\n>> Prevención: ambos bloquean en el mismo orden (ORDER BY reserva_id ... FOR UPDATE)")
A.execute("BEGIN"); B.execute("BEGIN")
A.execute(f"SELECT reserva_id FROM reserva WHERE reserva_id IN ({R2},{R1}) ORDER BY reserva_id FOR UPDATE"); log("A", "bloquea 1000 y 2000 en orden")
res = []; h = ejecutar_b(f"SELECT reserva_id FROM reserva WHERE reserva_id IN ({R1},{R2}) ORDER BY reserva_id FOR UPDATE", res)
time.sleep(1); A.execute("COMMIT"); log("A", "COMMIT"); h.join(); B.execute("COMMIT")

# ======================================================================
titulo("PUNTO 42 — Diagnóstico: mensajes del log del servidor")
for c_ in (A, B, M):
    c_.close()
print("FIN")
