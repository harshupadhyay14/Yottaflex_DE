"""Reconciliation / validation report: source->target counts, keys, RI, derived fields, labels."""
import json
from pathlib import Path

import duckdb


def _one(con, sql):
    return con.execute(sql).fetchone()[0]


def run_checks(db_path, labels_path=None, run_id=None):
    con = duckdb.connect(str(db_path), read_only=True)
    checks = []

    def add(name, expected, actual):
        checks.append({"check": name, "expected": expected, "actual": actual, "pass": expected == actual})

    if run_id is None:
        row = con.execute("SELECT run_id FROM run_log WHERE status='success' ORDER BY started_at DESC LIMIT 1").fetchone()
        run_id = row[0] if row else None
    # 1. every table, every run: input = accepted + rejected + malformed
    for rid, t, i, m, r, a in con.execute("SELECT run_id, table_name, input_rows, malformed_rows, rejected_rows, accepted_rows FROM run_metrics ORDER BY 1,2").fetchall():
        add(f"[{rid}] {t}: input_rows == accepted + rejected + malformed", i, a + r + m)
    # 2. keys unique
    for t, k in [("customers", "customer_id"), ("products", "product_id"), ("orders", "order_id"), ("order_items", "order_item_id")]:
        add(f"{t}: primary key {k} unique (dup keys = 0)", 0, _one(con, f"SELECT count(*) - count(DISTINCT {k}) FROM {t}"))
    add("orders_history: (order_id, updated_at) unique", 0, _one(con, "SELECT count(*) - (SELECT count(*) FROM (SELECT DISTINCT order_id, updated_at FROM orders_history)) FROM orders_history"))
    # 3. referential integrity
    add("orders -> customers: orphans = 0", 0, _one(con, "SELECT count(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM customers c WHERE c.customer_id=o.customer_id)"))
    add("order_items -> orders: orphans = 0", 0, _one(con, "SELECT count(*) FROM order_items i WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id=i.order_id)"))
    add("order_items -> products: orphans = 0", 0, _one(con, "SELECT count(*) FROM order_items i WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.product_id=i.product_id)"))
    # 4. derived fields / history consistency / rollup
    add("order_items: line_total == quantity * unit_price (violations = 0)", 0, _one(con, "SELECT count(*) FROM order_items WHERE line_total <> quantity * unit_price"))
    add("orders: current row == latest history version (mismatches = 0)", 0, _one(con, """SELECT count(*) FROM orders o JOIN
        (SELECT order_id, max(updated_at) mu FROM orders_history GROUP BY 1) h USING (order_id) WHERE o.updated_at <> h.mu"""))
    add("orders: every order has history (missing = 0)", 0, _one(con, "SELECT count(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM orders_history h WHERE h.order_id=o.order_id)"))
    base = _one(con, "SELECT coalesce(sum(i.line_total),0) FROM orders o JOIN order_items i USING(order_id) WHERE o.status='completed'")
    add("completed revenue: base tables == daily rollup", float(base), float(_one(con, "SELECT coalesce(sum(revenue),0) FROM agg_daily_category_revenue")))
    # 5. rejects traceable
    add("rejects: rows missing source_file/source_row/reason = 0", 0, _one(con, "SELECT count(*) FROM rejects WHERE source_file IS NULL OR source_row IS NULL OR reason IS NULL"))
    add("rejects: reject_id unique within a run (dups = 0)", 0, _one(con, "SELECT count(*) FROM (SELECT run_id, reject_id FROM rejects GROUP BY 1,2 HAVING count(*)>1)"))
    add("rejects == sum(rejected + malformed) in run_metrics", _one(con, "SELECT coalesce(sum(rejected_rows+malformed_rows),0) FROM run_metrics WHERE run_id IN (SELECT run_id FROM run_log WHERE status='success')"),
        _one(con, "SELECT count(*) FROM rejects WHERE run_id IN (SELECT run_id FROM run_log WHERE status='success')"))
    # 6. expected-answer labels (kept outside the input data)
    if labels_path and run_id:
        meta = json.loads(Path(labels_path).read_text())
        for t, n in meta["input_rows"].items():
            add(f"[{run_id}] labels: {t} input_rows", n, _one(con, f"SELECT input_rows FROM run_metrics WHERE run_id='{run_id}' AND table_name='{t}'"))
        for t, reasons in meta["expected_rejects"].items():
            actual = dict(con.execute("SELECT reason, count(*) FROM rejects WHERE run_id=? AND table_name=? GROUP BY 1", [run_id, t]).fetchall())
            for reason in sorted(set(reasons) | set(actual)):
                add(f"[{run_id}] labels: {t}.{reason} rejects", reasons.get(reason, 0), actual.get(reason, 0))
    con.close()
    return checks


def render_markdown(checks, db_path):
    ok = sum(c["pass"] for c in checks)
    lines = [f"# Reconciliation report\n", f"Database: `{db_path}`  \nResult: **{ok}/{len(checks)} checks passed**\n",
             "| # | Check | Expected | Actual | Result |", "|---|-------|----------|--------|--------|"]
    for n, c in enumerate(checks, 1):
        lines.append(f"| {n} | {c['check']} | {c['expected']} | {c['actual']} | {'PASS' if c['pass'] else '**FAIL**'} |")
    return "\n".join(lines) + "\n"
