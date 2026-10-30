"""Baseline vs optimised workload: median wall-clock over N runs, result-equality check, EXPLAIN ANALYZE plans."""
import platform
import statistics
import time
from pathlib import Path

import duckdb

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def _norm(rows):
    def f(v):
        return round(float(v), 2) if hasattr(v, "as_tuple") or isinstance(v, float) else v
    return sorted(tuple(f(v) for v in r) for r in rows)


def _time(con, sql, runs):
    con.execute(sql).fetchall()  # warm-up (not counted)
    ts = []
    for _ in range(runs):
        t = time.perf_counter()
        con.execute(sql).fetchall()
        ts.append((time.perf_counter() - t) * 1000)
    return statistics.median(ts), min(ts)


def run_benchmark(db_path, out_md, runs=7, sql_dir=SQL_DIR):
    con = duckdb.connect(str(db_path), read_only=True)
    sizes = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("customers", "orders", "order_items", "agg_daily_category_revenue")}
    out_md = Path(out_md)
    plan_dir = out_md.parent / "explain"
    plan_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for base in sorted((Path(sql_dir) / "baseline").glob("*.sql")):
        name = base.stem
        b_sql, o_sql = base.read_text(), (Path(sql_dir) / "optimized" / base.name).read_text()
        same = _norm(con.execute(b_sql).fetchall()) == _norm(con.execute(o_sql).fetchall())
        (b_med, b_min), (o_med, o_min) = _time(con, b_sql, runs), _time(con, o_sql, runs)
        for tag, sql in (("baseline", b_sql), ("optimized", o_sql)):
            plan = "\n".join(r[1] for r in con.execute("EXPLAIN ANALYZE " + sql).fetchall())
            (plan_dir / f"{name}_{tag}.txt").write_text(plan, encoding="utf-8")
        rows.append((name, b_med, o_med, b_med / o_med if o_med else float("inf"), same))
    con.close()
    md = ["# Performance benchmark: baseline vs optimised\n",
          f"Engine: DuckDB {duckdb.__version__} on Python {platform.python_version()} ({platform.machine()}). "
          f"Median of {runs} timed runs after 1 warm-up. Rows: " + ", ".join(f"{k}={v:,}" for k, v in sizes.items()) + ".\n",
          "| Query | Baseline median (ms) | Optimised median (ms) | Speed-up | Results identical |", "|---|---:|---:|---:|:---:|"]
    for n, b, o, s, same in rows:
        md.append(f"| {n} | {b:.1f} | {o:.1f} | {s:.1f}x | {'yes' if same else '**NO**'} |")
    md += ["", "Optimisations applied (see `sql/optimized/`): (1) pre-aggregated `agg_daily_category_revenue` rollup built at publish time "
           "(Q1), (2) pre-aggregate lines to order grain before joining + column pruning instead of `SELECT *` (Q2), "
           "(3) sargable range predicates instead of `strftime()/lower()` on columns and NOT EXISTS anti-join (Q3).",
           "", "EXPLAIN ANALYZE plans for every query are in `reports/explain/`.",
           "", "Caveat: single-machine, warm-cache, in-process engine; absolute numbers vary by hardware, ratios are what matter. "
           "Q2/Q3 gains are smaller because DuckDB's optimiser already pushes down many filters; the rollup (Q1) is the big win."]
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    return rows
