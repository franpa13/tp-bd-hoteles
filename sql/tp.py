"""
Utilidades comunes de medición (metodología del Punto 22).

- bench(): ejecuta la consulta 1 vez de calentamiento + N repeticiones,
  trae todas las filas al cliente y devuelve la mediana en ms.
- plan(): EXPLAIN (ANALYZE, BUFFERS) de la consulta.
- Todas las mediciones se imprimen en el log del script que las usa.
"""
import os, statistics, time, re
import psycopg

DSN = (f"host={os.getenv('PGHOST', 'localhost')} port={os.getenv('PGPORT', '5432')} "
       f"user={os.getenv('PGUSER', 'postgres')} password={os.getenv('PGPASSWORD', 'postgres')} "
       f"dbname={os.getenv('PGDATABASE', 'hoteles')} options=-csearch_path=hotel,public")


def conectar(autocommit=True):
    # prepare_threshold=None: sin sentencias preparadas automáticas, para que cada
    # repetición se planifique de nuevo y respete los SET enable_* de los experimentos
    c = psycopg.connect(DSN, autocommit=autocommit, prepare_threshold=None)
    c.execute("SET max_parallel_workers_per_gather = 0")  # resultados más estables en 2 núcleos
    return c


def titulo(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78, flush=True)


def bench(c, sql, params=None, reps=5, warm=1):
    for _ in range(warm):
        c.execute(sql, params).fetchall()
    ts, n = [], 0
    for _ in range(reps):
        t = time.perf_counter()
        n = len(c.execute(sql, params).fetchall())
        ts.append((time.perf_counter() - t) * 1000)
    return statistics.median(ts), n


def plan(c, sql, params=None, analyze=True):
    opts = "ANALYZE, BUFFERS" if analyze else "COSTS"
    rows = c.execute(f"EXPLAIN ({opts}) {sql}", params).fetchall()
    return "\n".join(r[0] for r in rows)


def resumen_plan(texto):
    """Primer nodo, buffers totales y tiempo de ejecución del plan."""
    nodos = re.findall(r"(Seq Scan|Index Only Scan|Index Scan|Bitmap Heap Scan|Bitmap Index Scan|"
                       r"Hash Join|Nested Loop|Merge Join|Sort|HashAggregate|GroupAggregate|"
                       r"Parallel Seq Scan|Append|Materialize)( using \S+)?( on \S+)?", texto)
    buf = re.search(r"Buffers: (shared [^\n]+)", texto)
    ex = re.search(r"Execution Time: ([\d.]+) ms", texto)
    return {
        "nodos": [" ".join(x for x in n if x).strip() for n in nodos[:6]],
        "buffers": buf.group(1) if buf else "",
        "ms": float(ex.group(1)) if ex else None,
    }


def medir(c, etiqueta, sql, params=None, reps=5, mostrar_plan=True):
    ms, n = bench(c, sql, params, reps)
    p = plan(c, sql, params)
    r = resumen_plan(p)
    print(f"\n--- {etiqueta}\nmediana {ms:.2f} ms | filas {n} | {r['buffers']}\nnodos: {r['nodos']}")
    if mostrar_plan:
        print(p)
    return ms, r


def tam(c, rel):
    return c.execute("SELECT pg_size_pretty(pg_relation_size(%s::regclass)), pg_relation_size(%s::regclass)",
                     (rel, rel)).fetchone()
