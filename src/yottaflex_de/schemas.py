"""Source schemas (what we expect in the CSV files) and target DDL."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Col:
    name: str
    required: bool = True


SCHEMAS = {
    "customers": [Col("customer_id"), Col("name", False), Col("email"), Col("country"), Col("signup_ts")],
    "products": [Col("product_id"), Col("name"), Col("category"), Col("unit_price")],
    "orders": [Col("order_id"), Col("customer_id"), Col("order_ts"), Col("status"), Col("updated_at")],
    "order_items": [Col("order_item_id"), Col("order_id"), Col("product_id"), Col("quantity"), Col("unit_price")],
}
TABLE_ORDER = ["customers", "products", "orders", "order_items"]  # parents before children
VALID_STATUSES = ["placed", "paid", "shipped", "completed", "cancelled", "returned"]
MIN_QTY, MAX_QTY = 1, 10000

DDL = """
CREATE TABLE IF NOT EXISTS customers (
  customer_id VARCHAR NOT NULL, name VARCHAR, email VARCHAR NOT NULL, country VARCHAR NOT NULL,
  signup_ts TIMESTAMP NOT NULL, run_id VARCHAR NOT NULL, source_file VARCHAR NOT NULL);
CREATE TABLE IF NOT EXISTS products (
  product_id VARCHAR NOT NULL, name VARCHAR NOT NULL, category VARCHAR NOT NULL,
  unit_price DECIMAL(12,2) NOT NULL, run_id VARCHAR NOT NULL, source_file VARCHAR NOT NULL);
CREATE TABLE IF NOT EXISTS orders (
  order_id VARCHAR NOT NULL, customer_id VARCHAR NOT NULL, order_ts TIMESTAMP NOT NULL,
  status VARCHAR NOT NULL, updated_at TIMESTAMP NOT NULL, run_id VARCHAR NOT NULL, source_file VARCHAR NOT NULL);
CREATE TABLE IF NOT EXISTS orders_history (
  order_id VARCHAR NOT NULL, customer_id VARCHAR NOT NULL, order_ts TIMESTAMP NOT NULL,
  status VARCHAR NOT NULL, updated_at TIMESTAMP NOT NULL, run_id VARCHAR NOT NULL, source_file VARCHAR NOT NULL);
CREATE TABLE IF NOT EXISTS order_items (
  order_item_id VARCHAR NOT NULL, order_id VARCHAR NOT NULL, product_id VARCHAR NOT NULL,
  quantity INTEGER NOT NULL, unit_price DECIMAL(12,2) NOT NULL, line_total DECIMAL(14,2) NOT NULL,
  run_id VARCHAR NOT NULL, source_file VARCHAR NOT NULL);
CREATE TABLE IF NOT EXISTS rejects (
  run_id VARCHAR NOT NULL, reject_id VARCHAR NOT NULL, table_name VARCHAR NOT NULL,
  source_file VARCHAR NOT NULL, source_row BIGINT NOT NULL, reason VARCHAR NOT NULL,
  raw_record VARCHAR, rejected_at TIMESTAMP NOT NULL);
CREATE TABLE IF NOT EXISTS run_log (
  run_id VARCHAR NOT NULL, input_hash VARCHAR, status VARCHAR NOT NULL, started_at TIMESTAMP NOT NULL,
  ended_at TIMESTAMP, as_of TIMESTAMP, input_rows BIGINT, accepted_rows BIGINT, rejected_rows BIGINT,
  failure_reason VARCHAR, notes VARCHAR);
CREATE TABLE IF NOT EXISTS run_metrics (
  run_id VARCHAR NOT NULL, table_name VARCHAR NOT NULL, input_rows BIGINT, malformed_rows BIGINT,
  rejected_rows BIGINT, accepted_rows BIGINT, inserted_rows BIGINT, updated_rows BIGINT,
  unchanged_rows BIGINT, stale_skipped_rows BIGINT, history_added_rows BIGINT);
"""
