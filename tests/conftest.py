import csv
from pathlib import Path

import pytest

HEADERS = {
    "customers": ["customer_id", "name", "email", "country", "signup_ts"],
    "products": ["product_id", "name", "category", "unit_price"],
    "orders": ["order_id", "customer_id", "order_ts", "status", "updated_at"],
    "order_items": ["order_item_id", "order_id", "product_id", "quantity", "unit_price"],
}
AS_OF = "2026-01-01 00:00:00"


def good_data():
    return {
        "customers": [["C1", "Ann", "ann@x.com", "IN", "2024-01-01T00:00:00Z"], ["C2", "Bob", "bob@x.com", "US", "2024-02-01T00:00:00Z"]],
        "products": [["P1", "Cable", "accessories", "10.00"], ["P2", "Phone", "devices", "200.50"]],
        "orders": [["O1", "C1", "2025-03-01T10:00:00Z", "completed", "2025-03-01T11:00:00Z"],
                   ["O2", "C2", "2025-03-02T10:00:00Z", "placed", "2025-03-02T10:30:00Z"]],
        "order_items": [["I1", "O1", "P1", "2", "10.00"], ["I2", "O1", "P2", "1", "200.50"], ["I3", "O2", "P1", "5", "10.00"]],
    }


def write_batch(directory: Path, data: dict, headers=None):
    directory.mkdir(parents=True, exist_ok=True)
    headers = headers or HEADERS
    for t, rows in data.items():
        with (directory / f"{t}.csv").open("w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            if headers.get(t) is not None:
                w.writerow(headers[t])
            w.writerows(rows)
    return directory


@pytest.fixture
def db(tmp_path):
    return tmp_path / "wh.duckdb"


@pytest.fixture
def batch(tmp_path):
    def make(name="b1", mutate=None, headers=None):
        d = good_data()
        if mutate:
            mutate(d)
        return write_batch(tmp_path / name, d, headers)
    return make


def q(db, sql, params=None):
    import duckdb
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()
