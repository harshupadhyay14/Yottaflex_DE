# Reconciliation report

Database: `output/warehouse.duckdb`  
Result: **43/43 checks passed**

| # | Check | Expected | Actual | Result |
|---|-------|----------|--------|--------|
| 1 | [run_20261030T174652Z_c89bc1dc] customers: input_rows == accepted + rejected + malformed | 102 | 102 | PASS |
| 2 | [run_20261030T174652Z_c89bc1dc] order_items: input_rows == accepted + rejected + malformed | 2946 | 2946 | PASS |
| 3 | [run_20261030T174652Z_c89bc1dc] orders: input_rows == accepted + rejected + malformed | 1025 | 1025 | PASS |
| 4 | [run_20261030T174652Z_c89bc1dc] products: input_rows == accepted + rejected + malformed | 21 | 21 | PASS |
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
| 16 | completed revenue: base tables == daily rollup | 1034217.25 | 1034217.25 | PASS |
| 17 | rejects: rows missing source_file/source_row/reason = 0 | 0 | 0 | PASS |
| 18 | rejects: reject_id unique within a run (dups = 0) | 0 | 0 | PASS |
| 19 | rejects == sum(rejected + malformed) in run_metrics | 102 | 102 | PASS |
| 20 | [run_20261030T174652Z_c89bc1dc] labels: customers input_rows | 102 | 102 | PASS |
| 21 | [run_20261030T174652Z_c89bc1dc] labels: order_items input_rows | 2946 | 2946 | PASS |
| 22 | [run_20261030T174652Z_c89bc1dc] labels: orders input_rows | 1025 | 1025 | PASS |
| 23 | [run_20261030T174652Z_c89bc1dc] labels: products input_rows | 21 | 21 | PASS |
| 24 | [run_20261030T174652Z_c89bc1dc] labels: customers.duplicate_key rejects | 2 | 2 | PASS |
| 25 | [run_20261030T174652Z_c89bc1dc] labels: customers.invalid_country rejects | 1 | 1 | PASS |
| 26 | [run_20261030T174652Z_c89bc1dc] labels: customers.missing_email rejects | 1 | 1 | PASS |
| 27 | [run_20261030T174652Z_c89bc1dc] labels: order_items.duplicate_key rejects | 9 | 9 | PASS |
| 28 | [run_20261030T174652Z_c89bc1dc] labels: order_items.invalid_order_ref rejects | 6 | 6 | PASS |
| 29 | [run_20261030T174652Z_c89bc1dc] labels: order_items.invalid_product_ref rejects | 9 | 9 | PASS |
| 30 | [run_20261030T174652Z_c89bc1dc] labels: order_items.invalid_quantity rejects | 8 | 8 | PASS |
| 31 | [run_20261030T174652Z_c89bc1dc] labels: order_items.malformed_row_field_count rejects | 3 | 3 | PASS |
| 32 | [run_20261030T174652Z_c89bc1dc] labels: order_items.missing_quantity rejects | 1 | 1 | PASS |
| 33 | [run_20261030T174652Z_c89bc1dc] labels: order_items.parent_order_rejected rejects | 38 | 38 | PASS |
| 34 | [run_20261030T174652Z_c89bc1dc] labels: orders.duplicate_key rejects | 5 | 5 | PASS |
| 35 | [run_20261030T174652Z_c89bc1dc] labels: orders.future_order_ts rejects | 2 | 2 | PASS |
| 36 | [run_20261030T174652Z_c89bc1dc] labels: orders.invalid_customer_ref rejects | 5 | 5 | PASS |
| 37 | [run_20261030T174652Z_c89bc1dc] labels: orders.invalid_order_ts rejects | 2 | 2 | PASS |
| 38 | [run_20261030T174652Z_c89bc1dc] labels: orders.invalid_status rejects | 3 | 3 | PASS |
| 39 | [run_20261030T174652Z_c89bc1dc] labels: orders.malformed_row_field_count rejects | 2 | 2 | PASS |
| 40 | [run_20261030T174652Z_c89bc1dc] labels: orders.missing_customer_id rejects | 2 | 2 | PASS |
| 41 | [run_20261030T174652Z_c89bc1dc] labels: products.duplicate_key rejects | 1 | 1 | PASS |
| 42 | [run_20261030T174652Z_c89bc1dc] labels: products.invalid_unit_price rejects | 1 | 1 | PASS |
| 43 | [run_20261030T174652Z_c89bc1dc] labels: products.missing_category rejects | 1 | 1 | PASS |
