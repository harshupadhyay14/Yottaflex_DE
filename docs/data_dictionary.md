# Data dictionary

## Source files (CSV, UTF-8, header required)
| File | Column | Type (target) | Req | Rules |
|---|---|---|---|---|
| customers.csv | customer_id | VARCHAR | Y | PK, unique per batch (last wins) |
| | name | VARCHAR | N | optional; NULL allowed |
| | email | VARCHAR | Y | `x@y.z` shape |
| | country | VARCHAR | Y | ISO-2 uppercase |
| | signup_ts | TIMESTAMP (UTC) | Y | ISO-8601 `YYYY-MM-DDTHH:MM:SSZ` |
| products.csv | product_id | VARCHAR | Y | PK |
| | name, category | VARCHAR | Y | |
| | unit_price | DECIMAL(12,2) | Y | numeric, >= 0 |
| orders.csv | order_id | VARCHAR | Y | entity key; (order_id, updated_at) = version key |
| | customer_id | VARCHAR | Y | FK -> customers (target or same batch) |
| | order_ts | TIMESTAMP (UTC) | Y | ISO-8601, not after `--as-of` |
| | status | VARCHAR | Y | placed, paid, shipped, completed, cancelled, returned |
| | updated_at | TIMESTAMP (UTC) | Y | ISO-8601; version timestamp |
| order_items.csv | order_item_id | VARCHAR | Y | PK |
| | order_id | VARCHAR | Y | FK -> orders |
| | product_id | VARCHAR | Y | FK -> products |
| | quantity | INTEGER | Y | 1..10000 |
| | unit_price | DECIMAL(12,2) | Y | >= 0 (price at order time) |

## Target tables
All target rows also have `run_id` (run that wrote it) and `source_file`.
- `customers`, `products`, `orders` (latest version), `orders_history` (all versions, unique on `(order_id, updated_at)`), `order_items` (+ derived `line_total DECIMAL(14,2) = quantity * unit_price`).
- `agg_daily_category_revenue(order_date, category, orders, units, revenue)`: completed orders only; rebuilt every run.

## Operational tables
- `rejects(run_id, reject_id, table_name, source_file, source_row, reason, raw_record, rejected_at)`: `source_row` = line number in the file (header = 1); `raw_record` = original record as JSON array; `reject_id = md5(table|file|row)[:16]`.
- `run_log(run_id, input_hash, status[running|success|failed|skipped_duplicate_input], started_at, ended_at, as_of, input_rows, accepted_rows, rejected_rows, failure_reason, notes)`.
- `run_metrics(run_id, table_name, input_rows, malformed_rows, rejected_rows, accepted_rows, inserted_rows, updated_rows, unchanged_rows, stale_skipped_rows, history_added_rows)`. Invariant: `input = accepted + rejected + malformed`.

## Labels (kept separate from inputs)
`data/sample_labels/expected_rejects.json` (and `data/large_labels/`): per table and reason, how many defective rows the generator injected, plus input row counts. Used only by `reconcile` and tests.
