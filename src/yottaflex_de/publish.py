"""Idempotent publishing of accepted staging rows into the target tables.

Pattern: key-based upsert (DELETE matching keys + INSERT) inside ONE transaction, so a failure
rolls everything back and a re-run of the same input converges to the same state.
Orders are versioned: every (order_id, updated_at) is appended to orders_history (never
overwritten); `orders` holds the latest version and ignores stale / late-arriving older versions.
"""


def _n(con, sql):
    return con.execute(sql).fetchone()[0]


def _upsert(con, table, key, cols, run_id, extra_select=""):
    updated = _n(con, f"SELECT count(*) FROM stg_{table} s WHERE reason IS NULL AND EXISTS (SELECT 1 FROM {table} t WHERE t.{key} = s.{key})")
    accepted = _n(con, f"SELECT count(*) FROM stg_{table} WHERE reason IS NULL")
    con.execute(f"DELETE FROM {table} WHERE {key} IN (SELECT {key} FROM stg_{table} WHERE reason IS NULL)")
    sel = ", ".join(cols) + extra_select
    con.execute(f"INSERT INTO {table} SELECT {sel}, '{run_id}', _source_file FROM stg_{table} WHERE reason IS NULL")
    return dict(inserted_rows=accepted - updated, updated_rows=updated, unchanged_rows=0, stale_skipped_rows=0, history_added_rows=0)


def publish_customers(con, run_id):
    return _upsert(con, "customers", "customer_id", ["customer_id", "name", "email", "country", "signup_ts"], run_id)


def publish_products(con, run_id):
    return _upsert(con, "products", "product_id", ["product_id", "name", "category", "unit_price"], run_id)


def publish_order_items(con, run_id):
    return _upsert(con, "order_items", "order_item_id",
                   ["order_item_id", "order_id", "product_id", "quantity", "unit_price"], run_id,
                   extra_select=", CAST(quantity * unit_price AS DECIMAL(14,2)) AS line_total")


def publish_orders(con, run_id):
    cols = "order_id, customer_id, order_ts, status, updated_at"
    # 1) history: append every accepted version once (idempotent on (order_id, updated_at))
    hist = con.execute(f"""INSERT INTO orders_history SELECT {cols}, '{run_id}', _source_file FROM stg_orders s
                           WHERE reason IS NULL AND NOT EXISTS (SELECT 1 FROM orders_history h
                           WHERE h.order_id = s.order_id AND h.updated_at = s.updated_at)""").fetchone()[0]
    # 2) latest incoming version per order
    con.execute(f"""CREATE OR REPLACE TEMP TABLE stg_orders_latest AS
                    SELECT {cols}, _source_file FROM (SELECT *, row_number() OVER (PARTITION BY order_id ORDER BY updated_at DESC) AS latest_rn
                    FROM stg_orders WHERE reason IS NULL) WHERE latest_rn = 1""")
    stale = _n(con, "SELECT count(*) FROM stg_orders_latest s WHERE EXISTS (SELECT 1 FROM orders o WHERE o.order_id = s.order_id AND o.updated_at > s.updated_at)")
    same = _n(con, "SELECT count(*) FROM stg_orders_latest s WHERE EXISTS (SELECT 1 FROM orders o WHERE o.order_id = s.order_id AND o.updated_at = s.updated_at)")
    con.execute("""CREATE OR REPLACE TEMP TABLE orders_winners AS SELECT s.* FROM stg_orders_latest s WHERE NOT EXISTS
                   (SELECT 1 FROM orders o WHERE o.order_id = s.order_id AND o.updated_at >= s.updated_at)""")
    upd = _n(con, "SELECT count(*) FROM orders_winners w WHERE EXISTS (SELECT 1 FROM orders o WHERE o.order_id = w.order_id)")
    total = _n(con, "SELECT count(*) FROM orders_winners")
    con.execute("DELETE FROM orders WHERE order_id IN (SELECT order_id FROM orders_winners)")
    con.execute(f"INSERT INTO orders SELECT {cols}, '{run_id}', _source_file FROM orders_winners")
    return dict(inserted_rows=total - upd, updated_rows=upd, unchanged_rows=same, stale_skipped_rows=stale, history_added_rows=hist)


PUBLISHERS = {"customers": publish_customers, "products": publish_products,
              "orders": publish_orders, "order_items": publish_order_items}


def rebuild_rollup(con):
    """Pre-aggregated daily revenue (the optimisation used by the benchmark). Full deterministic rebuild."""
    con.execute("""CREATE OR REPLACE TABLE agg_daily_category_revenue AS
        SELECT CAST(o.order_ts AS DATE) AS order_date, p.category,
               count(DISTINCT o.order_id) AS orders, sum(i.quantity) AS units, sum(i.line_total) AS revenue
        FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN products p ON p.product_id = i.product_id
        WHERE o.status = 'completed' GROUP BY 1, 2""")
