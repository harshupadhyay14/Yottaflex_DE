"""Typing + business-rule validation in SQL. Produces one staging table per source table
(`stg_<table>`) with a single `reason` column: NULL = accepted, otherwise the reject reason.

Order of checks per row: required fields -> format/type -> business rules -> duplicate key
-> referential integrity. First failing check wins, so each rejected row has exactly one reason.
"""
import pandas as pd

from .schemas import MAX_QTY, MIN_QTY, SCHEMAS, VALID_STATUSES

TS_RE = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


def _ts(c):      # ISO-8601 UTC text -> TIMESTAMP (NULL if malformed)
    return f"TRY_CAST(regexp_replace({c}, 'Z$', '') AS TIMESTAMP)"


def _bad_ts(c):
    return f"NOT (regexp_matches({c}, '{TS_RE}') AND {_ts(c)} IS NOT NULL)"


def _dec(c):
    return f"TRY_CAST({c} AS DECIMAL(12,2))"


STATUS_LIST = ",".join(f"'{s}'" for s in VALID_STATUSES)

# typed projection (alias = target column name)
TYPED = {
    "customers": ["customer_id", "name", "email", "country", f"{_ts('signup_ts')} AS signup_ts"],
    "products": ["product_id", "name", "category", f"{_dec('unit_price')} AS unit_price"],
    "orders": ["order_id", "customer_id", f"{_ts('order_ts')} AS order_ts", "status", f"{_ts('updated_at')} AS updated_at"],
    "order_items": ["order_item_id", "order_id", "product_id", "TRY_CAST(quantity AS INTEGER) AS quantity",
                    f"{_dec('unit_price')} AS unit_price"],
}


def _checks(table, as_of):
    req = [(f"missing_{c.name}", f"{c.name} IS NULL") for c in SCHEMAS[table] if c.required]
    fmt = {
        "customers": [("invalid_signup_ts", _bad_ts("signup_ts")),
                      ("invalid_email", r"NOT regexp_matches(email, '^[^@\s]+@[^@\s]+\.[^@\s]+$')"),
                      ("invalid_country", "NOT regexp_matches(country, '^[A-Z]{2}$')")],
        "products": [("invalid_unit_price", f"{_dec('unit_price')} IS NULL OR {_dec('unit_price')} < 0")],
        "orders": [("invalid_order_ts", _bad_ts("order_ts")), ("invalid_updated_at", _bad_ts("updated_at")),
                   ("invalid_status", f"status NOT IN ({STATUS_LIST})"),
                   ("future_order_ts", f"{_ts('order_ts')} > TIMESTAMP '{as_of}'")],
        "order_items": [("invalid_quantity",
                         f"TRY_CAST(quantity AS INTEGER) IS NULL OR TRY_CAST(quantity AS INTEGER) NOT BETWEEN {MIN_QTY} AND {MAX_QTY}"),
                        ("invalid_unit_price", f"{_dec('unit_price')} IS NULL OR {_dec('unit_price')} < 0")],
    }[table]
    return req + fmt


# duplicate-event key per table (orders: one row per (order, version))
DUP_KEY = {"customers": "customer_id", "products": "product_id", "orders": "order_id, updated_at",
           "order_items": "order_item_id"}


def stage(con, table, rows, as_of):
    """Load text rows into raw_<table>, then build stg_<table> with typed columns + reason."""
    names = [c.name for c in SCHEMAS[table]]
    coldefs = ", ".join(f"{n} VARCHAR" for n in names)
    con.execute(f"CREATE OR REPLACE TEMP TABLE raw_{table} ({coldefs}, _source_file VARCHAR, _source_row BIGINT, _raw VARCHAR)")
    if rows:
        df = pd.DataFrame(rows, columns=names + ["_source_file", "_source_row", "_raw"], dtype=object)
        con.register("_df", df)
        con.execute(f"INSERT INTO raw_{table} SELECT {', '.join(names)}, _source_file, _source_row, _raw FROM _df")
        con.unregister("_df")
    case = "CASE " + " ".join(f"WHEN {cond} THEN '{reason}'" for reason, cond in _checks(table, as_of)) + " END"
    typed = ", ".join(TYPED[table])
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE stg_{table} AS
        SELECT *, COALESCE(reason0, CASE WHEN rn > 1 THEN 'duplicate_key' END) AS reason
        FROM (
          SELECT t.*, row_number() OVER (PARTITION BY {DUP_KEY[table]}, (reason0 IS NULL)
                                         ORDER BY _source_row DESC) AS rn
          FROM (SELECT {typed}, _source_file, _source_row, _raw, {case} AS reason0 FROM raw_{table}) t
        ) x""")


def check_references(con, table):
    """Referential integrity against target + accepted rows of this batch (parents staged first)."""
    if table == "orders":
        con.execute("""UPDATE stg_orders SET reason = 'invalid_customer_ref' WHERE reason IS NULL AND customer_id NOT IN
                       (SELECT customer_id FROM customers UNION SELECT customer_id FROM stg_customers WHERE reason IS NULL)""")
    elif table == "order_items":
        known_orders = "(SELECT order_id FROM orders UNION SELECT order_id FROM stg_orders WHERE reason IS NULL)"
        # parent exists in the batch but was rejected -> cascade (distinct, traceable reason)
        con.execute(f"""UPDATE stg_order_items SET reason = 'parent_order_rejected' WHERE reason IS NULL
                        AND order_id NOT IN {known_orders} AND order_id IN (SELECT order_id FROM stg_orders WHERE reason IS NOT NULL)""")
        con.execute(f"UPDATE stg_order_items SET reason = 'invalid_order_ref' WHERE reason IS NULL AND order_id NOT IN {known_orders}")
        con.execute("""UPDATE stg_order_items SET reason = 'invalid_product_ref' WHERE reason IS NULL AND product_id NOT IN
                       (SELECT product_id FROM products UNION SELECT product_id FROM stg_products WHERE reason IS NULL)""")


def stage_counts(con, table):
    total, accepted = con.execute(f"SELECT count(*), count(*) FILTER (WHERE reason IS NULL) FROM stg_{table}").fetchone()
    return total, accepted, total - accepted
