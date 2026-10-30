import argparse
import json
import logging
import sys

from .benchmark import run_benchmark
from .generate_data import generate
from .pipeline import run_pipeline
from .reconcile import render_markdown, run_checks


def main(argv=None):
    p = argparse.ArgumentParser(prog="yottaflex_de", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="generate seeded synthetic CSVs + separate label file")
    g.add_argument("--out", required=True); g.add_argument("--labels", required=True)
    g.add_argument("--orders", type=int, default=1000); g.add_argument("--seed", type=int, default=42)
    r = sub.add_parser("run", help="run the pipeline on a directory of CSVs")
    r.add_argument("--input", required=True); r.add_argument("--db", default="output/warehouse.duckdb")
    r.add_argument("--as-of", help="'YYYY-MM-DD HH:MM:SS' UTC; orders after this are rejected as future-dated")
    r.add_argument("--force", action="store_true", help="re-process an input that was already loaded successfully")
    r.add_argument("--fail-after", choices=["customers", "products", "orders", "order_items"], help="simulate a crash (demo/test)")
    r.add_argument("--metrics-dir", default="output/runs")
    c = sub.add_parser("reconcile", help="write reconciliation report")
    c.add_argument("--db", default="output/warehouse.duckdb"); c.add_argument("--labels"); c.add_argument("--run-id")
    c.add_argument("--out", default="reports/reconciliation.md")
    b = sub.add_parser("benchmark", help="baseline vs optimised workload timings")
    b.add_argument("--db", default="output/warehouse.duckdb"); b.add_argument("--out", default="reports/benchmark.md")
    b.add_argument("--runs", type=int, default=7)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if a.cmd == "generate":
        print(json.dumps(generate(a.out, a.labels, a.orders, a.seed), indent=2))
    elif a.cmd == "run":
        res = run_pipeline(a.input, a.db, as_of=a.as_of, force=a.force, fail_after=a.fail_after, metrics_dir=a.metrics_dir)
        print(json.dumps(res, indent=2, default=str))
        return 1 if res["status"] == "failed" else 0
    elif a.cmd == "reconcile":
        checks = run_checks(a.db, a.labels, a.run_id)
        from pathlib import Path
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(render_markdown(checks, a.db), encoding="utf-8")
        bad = [c for c in checks if not c["pass"]]
        print(f"{len(checks) - len(bad)}/{len(checks)} checks passed -> {a.out}")
        for c in bad:
            print("FAIL:", c)
        return 1 if bad else 0
    elif a.cmd == "benchmark":
        for n, bm, om, s, same in run_benchmark(a.db, a.out, a.runs):
            print(f"{n}: baseline {bm:.1f} ms, optimised {om:.1f} ms, {s:.1f}x, identical={same}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
