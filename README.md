# YottaFlex DE Challenge: orders pipeline + workload optimisation

A tested, idempotent data-engineering vertical slice: **ingest -> validate/quarantine -> transform -> publish -> reconcile -> benchmark**.
Python 3.10+, DuckDB (embedded, no services), pandas, pytest. Runs fully locally.

## Quick start (clean environment)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src                       # (Windows: set PYTHONPATH=src)

python -m pytest -q                         # 19 tests
python -m yottaflex_de run --input data/sample --db output/warehouse.duckdb --as-of "2026-01-01 00:00:00"
python -m yottaflex_de reconcile --db output/warehouse.duckdb --labels data/sample_labels/expected_rejects.json

# large, reproducible run (200k orders, ~600k items, ~35 MB of CSV)
python -m yottaflex_de generate --out data/large --labels data/large_labels --orders 200000 --seed 7
python -m yottaflex_de run --input data/large --db output/large.duckdb --as-of "2026-01-01 00:00:00"
python -m yottaflex_de reconcile --db output/large.duckdb --labels data/large_labels/expected_rejects.json --out reports/reconciliation.md
python -m yottaflex_de benchmark --db output/large.duckdb --out reports/benchmark.md
```
`make test | sample | run | large | reconcile | benchmark` wraps the same commands. `--as-of` pins "now" so the future-dated-order rule is deterministic.

## Architecture
```
 data/*/ *.csv ──► ingest.py ──► validate.py ──► publish.py ──► DuckDB warehouse ──► reconcile.py / benchmark.py
 (4 source files)  header/schema   typed staging   one TRANSACTION  customers, products,    reports/*.md
                   + row shape     + reason per    upsert + history orders, orders_history,
                   checks          row (SQL)       + rollup         order_items, rollup
                       │                │
                       └─ structural ───┴─► rejects (run_id, reject_id, table, source_file, source_row, reason, raw_record)
 pipeline.py orchestrates and writes run_log + run_metrics (+ output/runs/<run_id>.json)
```
1. **Ingest** reads everything as text. A missing *required* column aborts the batch (schema change); extra/reordered columns are tolerated with a warning; rows with the wrong field count are rejected with file + line number.
2. **Validate** (SQL, `stg_<table>`): required fields -> formats/types -> business rules -> duplicate key -> referential integrity. One `reason` per row (first failing check). Nothing touches target tables yet.
3. **Publish** (single transaction): key-based upsert of accepted rows, `orders_history` append, rejects, metrics, rollup rebuild. Any exception -> `ROLLBACK`.
4. **Reconcile / benchmark** read the result.

## Data model (details in `docs/data_dictionary.md`)
`customers(customer_id)` 1-N `orders(order_id)` 1-N `order_items(order_item_id)` N-1 `products(product_id)`.
`orders_history` keeps every version `(order_id, updated_at)`; `orders` is the latest version. Grain: one row per entity (items: one row per product line).

Naming: snake_case; deterministic IDs (`C000001`, `P00001`, `O0000001`, `I00000001`; `reject_id = md5(table|file|row)[:16]`); ISO-8601 UTC timestamps (`YYYY-MM-DDTHH:MM:SSZ`); every target row carries `run_id` + `source_file`; `run_id = run_<UTC ts>_<input hash[:8]>`.

## Rules & rejects
| Table | Reject reasons |
|---|---|
| all | `malformed_row_field_count`, `malformed_row_parse_error`, `missing_<required col>`, `duplicate_key` |
| customers | `invalid_signup_ts`, `invalid_email`, `invalid_country` (ISO-2 upper) |
| products | `invalid_unit_price` (non-numeric or < 0) |
| orders | `invalid_order_ts`, `invalid_updated_at`, `invalid_status` (placed/paid/shipped/completed/cancelled/returned), `future_order_ts` (> `--as-of`), `invalid_customer_ref` |
| order_items | `invalid_quantity` (int, 1..10000), `invalid_unit_price`, `parent_order_rejected` (order rejected in this batch), `invalid_order_ref`, `invalid_product_ref` |

Duplicates: same key twice in a batch -> **last row wins**, earlier ones go to `rejects` as `duplicate_key`. For orders the key is `(order_id, updated_at)`, so different versions of an order are *not* duplicates; they are history.

## Idempotency, retry, restart, backfill
- **Rerun same input**: input hash already `success` -> run recorded as `skipped_duplicate_input`, nothing changes. `--force` reprocesses; upserts converge (test `test_rerun_same_input...` asserts identical counts, `unchanged_rows`, 0 new history).
- **Partial failure**: one transaction; failure => rollback, `run_log.status='failed'` with `failure_reason`; failed runs never block a retry. Demo: `reports/failure_retry_demo.txt` (`--fail-after orders`).
- **Late / out-of-order data**: an incoming order version only replaces `orders` if its `updated_at` is strictly newer; older ones are counted in `stale_skipped_rows` but still appended to `orders_history`. Works across files and within a file.
- **Backfill**: feed any directory of older/newer files in any order; the `updated_at` guard makes the final state order-independent. Children may reference parents loaded in earlier batches.

## Observability
`run_log` (run_id, status, started/ended, input/accepted/rejected, failure_reason, notes/warnings), `run_metrics` per table (input, malformed, rejected, accepted, inserted, updated, unchanged, stale_skipped, history_added), `rejects`, structured logs with run_id, and `output/runs/<run_id>.json`.

## Evidence (all committed under `reports/`)
- `pytest_output.txt`: 19 passed. Covers happy path, empty (header-only + zero-byte), missing file, malformed rows, bad values, missing required/nulls, duplicates, schema change (fatal + tolerated), rerun/force, partial failure + retry, invalid refs + cascade, late-arriving, out-of-order, boundary values (qty 0/1/10000/10001, as-of boundary), generator reproducibility, **exact match of rejects vs injected labels**.
- `reconciliation.md`: 200k-order run, **43/43 checks** (counts, PK uniqueness, RI, derived fields, history consistency, rollup vs base revenue, reject traceability, injected labels).
- `benchmark.md` + `explain/`: baseline vs optimised (below). `failure_retry_demo.txt`.
- 200k run: 828k input rows ingested, validated and published in ~7 s (see `reports/runs/*.json`). 20,559 rejects, all reconciled to injected labels.

## Performance (200k orders / 586k items, median of 7)
| Query | Baseline | Optimised | Speed-up |
|---|---:|---:|---:|
| Q1 monthly revenue by category | 53.2 ms | 1.9 ms | 28x |
| Q2 top customers per country | 57.7 ms | 55.0 ms | 1.0x |
| Q3 inactive customers | 15.4 ms | 6.1 ms | 2.5x |

Baseline inefficiencies: `SELECT *` subqueries, function-wrapped (non-sargable) filters, late filtering, `NOT IN`, re-aggregating raw lines. **Main optimisation: pre-aggregated daily rollup** built in the publish transaction (Q1). Results are asserted identical. Q2's gain is small, since DuckDB already optimises much of it; I report that rather than hide it.

## Known limitations / next steps
- Target tables have no declared PK/FK constraints (DuckDB's delete+insert-in-one-transaction upsert conflicts with enforced PKs); uniqueness and RI are enforced by validation and re-checked by `reconcile`.
- Whole-file hash for run-level idempotency: a changed file is a new batch (row-level upserts still converge). No streaming/CDC.
- Rollup is rebuilt fully each run; at scale make it incremental per affected `order_date`.
- Dimensions (customers/products) are overwritten, not versioned (SCD2 would be the next step). Orders keep full history.
- Single writer (DuckDB); for multi-writer use Postgres/warehouse with the same SQL pattern (MERGE).
