# Performance benchmark: baseline vs optimised

Engine: DuckDB 2.0.0 on Python 3.12.2 (AMD64). Median of 7 timed runs after 1 warm-up. Rows: customers=19,600, orders=196,800, order_items=586,109, agg_daily_category_revenue=2,130.

| Query | Baseline median (ms) | Optimised median (ms) | Speed-up | Results identical |
|---|---:|---:|---:|:---:|
| q1_monthly_category_revenue | 53.2 | 1.9 | 28.2x | yes |
| q2_top_customers_per_country | 57.7 | 55.0 | 1.0x | yes |
| q3_inactive_customers | 15.4 | 6.1 | 2.5x | yes |

Optimisations applied (see `sql/optimized/`): (1) pre-aggregated `agg_daily_category_revenue` rollup built at publish time (Q1), (2) pre-aggregate lines to order grain before joining + column pruning instead of `SELECT *` (Q2), (3) sargable range predicates instead of `strftime()/lower()` on columns and NOT EXISTS anti-join (Q3).

EXPLAIN ANALYZE plans for every query are in `reports/explain/`.

Caveat: single-machine, warm-cache, in-process engine; absolute numbers vary by hardware, ratios are what matter. Q2/Q3 gains are smaller because DuckDB's optimiser already pushes down many filters; the rollup (Q1) is the big win.
