# Reconciliation report

Database: `output/large.duckdb`  
Result: **43/43 checks passed**

| # | Check | Expected | Actual | Result |
|---|-------|----------|--------|--------|
| 1 | [run_20261030T170211Z_02ee2b2c] customers: input_rows == accepted + rejected + malformed | 20400 | 20400 | PASS |
| 2 | [run_20261030T170211Z_02ee2b2c] order_items: input_rows == accepted + rejected + malformed | 601628 | 601628 | PASS |
| 3 | [run_20261030T170211Z_02ee2b2c] orders: input_rows == accepted + rejected + malformed | 205000 | 205000 | PASS |
| 4 | [run_20261030T170211Z_02ee2b2c] products: input_rows == accepted + rejected + malformed | 1020 | 1020 | PASS |
| 5 | customers: primary key customer_id unique (dup keys = 0) | 0 | 0 | PASS |
| 6 | products: primary key product_id unique (dup keys = 0) | 0 | 0 | PASS |
| 7 | orders: primary key order_id unique (dup keys = 0) | 0 | 0 | PASS |
| 8 | order_items: primary key order_item_id unique (dup keys = 0) | 0 | 0 | PASS |
| 9 | orders_history: (order_id, updated_at) unique | 0 | 0 | PASS |
| 10 | orders -> customers: orphans = 0 | 0 | 0 | PASS |
| 11 | order_items -> orders: orphans = 0 | 0 | 0 | PASS |
| 12 | order_items -> products: orphans = 0 | 0 | 0 | PASS |
| 13 | order_items: line_total == quantity * unit_price (violations = 0) | 0 | 0 | PASS |
| 14 | orders: current row == latest history version (mismatches = 0) | 0 | 0 | PASS |
| 15 | orders: every order has history (missing = 0) | 0 | 0 | PASS |
| 16 | completed revenue: base tables == daily rollup | 223061272.23 | 223061272.23 | PASS |
| 17 | rejects: rows missing source_file/source_row/reason = 0 | 0 | 0 | PASS |
| 18 | rejects: reject_id unique within a run (dups = 0) | 0 | 0 | PASS |
| 19 | rejects == sum(rejected + malformed) in run_metrics | 20559 | 20559 | PASS |
| 20 | [run_20261030T170211Z_02ee2b2c] labels: customers input_rows | 20400 | 20400 | PASS |
| 21 | [run_20261030T170211Z_02ee2b2c] labels: order_items input_rows | 601628 | 601628 | PASS |
| 22 | [run_20261030T170211Z_02ee2b2c] labels: orders input_rows | 205000 | 205000 | PASS |
| 23 | [run_20261030T170211Z_02ee2b2c] labels: products input_rows | 1020 | 1020 | PASS |
| 24 | [run_20261030T170211Z_02ee2b2c] labels: customers.duplicate_key rejects | 400 | 400 | PASS |
| 25 | [run_20261030T170211Z_02ee2b2c] labels: customers.invalid_country rejects | 200 | 200 | PASS |
| 26 | [run_20261030T170211Z_02ee2b2c] labels: customers.missing_email rejects | 200 | 200 | PASS |
| 27 | [run_20261030T170211Z_02ee2b2c] labels: order_items.duplicate_key rejects | 1771 | 1771 | PASS |
| 28 | [run_20261030T170211Z_02ee2b2c] labels: order_items.invalid_order_ref rejects | 1183 | 1183 | PASS |
| 29 | [run_20261030T170211Z_02ee2b2c] labels: order_items.invalid_product_ref rejects | 1771 | 1771 | PASS |
| 30 | [run_20261030T170211Z_02ee2b2c] labels: order_items.invalid_quantity rejects | 1417 | 1417 | PASS |
| 31 | [run_20261030T170211Z_02ee2b2c] labels: order_items.malformed_row_field_count rejects | 590 | 590 | PASS |
| 32 | [run_20261030T170211Z_02ee2b2c] labels: order_items.missing_quantity rejects | 354 | 354 | PASS |
| 33 | [run_20261030T170211Z_02ee2b2c] labels: order_items.parent_order_rejected rejects | 8433 | 8433 | PASS |
| 34 | [run_20261030T170211Z_02ee2b2c] labels: orders.duplicate_key rejects | 1000 | 1000 | PASS |
| 35 | [run_20261030T170211Z_02ee2b2c] labels: orders.future_order_ts rejects | 400 | 400 | PASS |
| 36 | [run_20261030T170211Z_02ee2b2c] labels: orders.invalid_customer_ref rejects | 1000 | 1000 | PASS |
| 37 | [run_20261030T170211Z_02ee2b2c] labels: orders.invalid_order_ts rejects | 400 | 400 | PASS |
| 38 | [run_20261030T170211Z_02ee2b2c] labels: orders.invalid_status rejects | 600 | 600 | PASS |
| 39 | [run_20261030T170211Z_02ee2b2c] labels: orders.malformed_row_field_count rejects | 400 | 400 | PASS |
| 40 | [run_20261030T170211Z_02ee2b2c] labels: orders.missing_customer_id rejects | 400 | 400 | PASS |
| 41 | [run_20261030T170211Z_02ee2b2c] labels: products.duplicate_key rejects | 20 | 20 | PASS |
| 42 | [run_20261030T170211Z_02ee2b2c] labels: products.invalid_unit_price rejects | 10 | 10 | PASS |
| 43 | [run_20261030T170211Z_02ee2b2c] labels: products.missing_category rejects | 10 | 10 | PASS |
