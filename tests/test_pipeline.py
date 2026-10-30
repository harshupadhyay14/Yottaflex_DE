import json

import pytest

from conftest import AS_OF, HEADERS, good_data, q, write_batch
from yottaflex_de.generate_data import generate
from yottaflex_de.pipeline import run_pipeline
from yottaflex_de.reconcile import run_checks


def run(batch, db, **kw):
    return run_pipeline(batch, db, as_of=AS_OF, **kw)


def reasons(db, table):
    return dict(q(db, "SELECT reason, count(*) FROM rejects WHERE table_name=? GROUP BY 1", [table]))


# ---------------------------------------------------------------- happy path
def test_happy_path_loads_everything_and_reconciles(batch, db):
    r = run(batch(), db)
    assert r["status"] == "success"
    assert q(db, "SELECT count(*) FROM customers")[0][0] == 2
    assert q(db, "SELECT count(*) FROM order_items")[0][0] == 3
    assert q(db, "SELECT count(*) FROM rejects")[0][0] == 0
    # derived field is deterministic: 2*10.00, 1*200.50, 5*10.00
    assert q(db, "SELECT sum(line_total) FROM order_items")[0][0] == pytest.approx(270.50)
    assert all(c["pass"] for c in run_checks(db)), [c for c in run_checks(db) if not c["pass"]]
    log = q(db, "SELECT status, input_rows, accepted_rows, rejected_rows, ended_at IS NOT NULL FROM run_log")[0]
    assert log == ("success", 9, 9, 0, True)


# ---------------------------------------------------------------- empty input
def test_empty_batch_header_only_and_zero_byte(batch, db, tmp_path):
    d = write_batch(tmp_path / "empty", {t: [] for t in HEADERS})
    (d / "orders.csv").write_text("")  # zero-byte file too
    r = run(d, db)
    assert r["status"] == "success"
    assert all(m["input_rows"] == 0 for m in r["tables"].values())
    assert q(db, "SELECT count(*) FROM orders")[0][0] == 0


def test_missing_input_file_fails_cleanly(batch, db):
    b = batch()
    (b / "products.csv").unlink()
    r = run(b, db)
    assert r["status"] == "failed" and "missing_input_file" in r["failure_reason"]
    assert q(db, "SELECT count(*) FROM customers")[0][0] == 0


# ---------------------------------------------------------------- malformed records
def test_malformed_rows_are_rejected_with_source_row(tmp_path, db):
    d = write_batch(tmp_path / "m", good_data())
    with (d / "orders.csv").open("a") as f:
        f.write("O9,C1,2025-03-03T10:00:00Z\n")                       # too few fields (line 4)
        f.write("O10,C1,2025-03-03T10:00:00Z,placed,2025-03-03T10:00:00Z,extra\n")  # too many (line 5)
    r = run(d, db)
    assert r["status"] == "success"
    assert reasons(db, "orders") == {"malformed_row_field_count": 2}
    rows = q(db, "SELECT source_file, source_row, raw_record FROM rejects ORDER BY source_row")
    assert [(a, b) for a, b, _ in rows] == [("orders.csv", 4), ("orders.csv", 5)]
    assert "O9" in rows[0][2]                                          # raw record preserved


def test_bad_values_become_rejects_not_crashes(batch, db):
    def m(d):
        d["orders"].append(["O3", "C1", "not-a-date", "placed", "2025-03-03T10:00:00Z"])
        d["order_items"].append(["I4", "O1", "P1", "abc", "10.00"])
        d["products"].append(["P3", "Bad", "x", "ten dollars"])
    assert run(batch(mutate=m), db)["status"] == "success"
    assert reasons(db, "orders") == {"invalid_order_ts": 1}
    assert reasons(db, "order_items") == {"invalid_quantity": 1}
    assert reasons(db, "products") == {"invalid_unit_price": 1}


# ---------------------------------------------------------------- nulls / missing required
def test_missing_required_fields(batch, db):
    def m(d):
        d["customers"].append(["C3", "NoEmail", "", "IN", "2024-01-01T00:00:00Z"])
        d["customers"].append(["", "NoId", "a@b.com", "IN", "2024-01-01T00:00:00Z"])
        d["customers"].append(["C4", "", "c4@b.com", "IN", "2024-01-01T00:00:00Z"])   # name is optional -> accepted
    run(batch(mutate=m), db)
    assert reasons(db, "customers") == {"missing_email": 1, "missing_customer_id": 1}
    assert q(db, "SELECT count(*) FROM customers WHERE customer_id='C4'")[0][0] == 1


# ---------------------------------------------------------------- duplicates
def test_duplicate_keys_last_row_wins_and_dup_is_traceable(batch, db):
    def m(d):
        d["customers"].append(["C1", "Ann (dup, last wins)", "ann@x.com", "IN", "2024-01-01T00:00:00Z"])
        d["order_items"].append(list(d["order_items"][0]))              # exact duplicate event
    run(batch(mutate=m), db)
    assert q(db, "SELECT name FROM customers WHERE customer_id='C1'")[0][0] == "Ann (dup, last wins)"
    assert reasons(db, "customers") == {"duplicate_key": 1}
    assert reasons(db, "order_items") == {"duplicate_key": 1}
    assert q(db, "SELECT count(*) FROM order_items")[0][0] == 3


# ---------------------------------------------------------------- schema change
def test_schema_change_missing_required_column_fails_and_loads_nothing(batch, db):
    h = dict(HEADERS, orders=["order_id", "customer_id", "order_ts", "status"])     # updated_at dropped
    b = batch(headers=h)
    r = run(b, db)
    assert r["status"] == "failed" and "schema_change" in r["failure_reason"] and "updated_at" in r["failure_reason"]
    assert q(db, "SELECT count(*) FROM customers")[0][0] == 0
    assert q(db, "SELECT status, failure_reason IS NOT NULL FROM run_log")[0] == ("failed", True)


def test_schema_change_extra_and_reordered_columns_tolerated(tmp_path, db):
    d = good_data()
    h = dict(HEADERS, customers=["country", "customer_id", "email", "signup_ts", "name", "loyalty_tier"])
    rows = [[c[3], c[0], c[2], c[4], c[1], "gold"] for c in d["customers"]]
    d["customers"] = rows
    r = run(write_batch(tmp_path / "s", d, h), db)
    assert r["status"] == "success" and any("loyalty_tier" in w for w in r["warnings"])
    assert q(db, "SELECT count(*) FROM customers WHERE country IN ('IN','US')")[0][0] == 2


# ---------------------------------------------------------------- idempotency / rerun
def test_rerun_same_input_is_skipped_and_forced_rerun_changes_nothing(batch, db):
    b = batch()
    assert run(b, db)["status"] == "success"
    snap = lambda: [q(db, f"SELECT count(*) FROM {t}")[0][0] for t in ("customers", "products", "orders", "orders_history", "order_items")]
    before = snap()
    assert run(b, db)["status"] == "skipped_duplicate_input"
    assert snap() == before
    forced = run(b, db, force=True)
    assert forced["status"] == "success" and snap() == before
    assert forced["tables"]["orders"]["unchanged_rows"] == 2 and forced["tables"]["orders"]["history_added_rows"] == 0
    assert all(c["pass"] for c in run_checks(db))


# ---------------------------------------------------------------- partial failure + retry
def test_partial_failure_rolls_back_and_retry_succeeds(batch, db):
    b = batch()
    r = run(b, db, fail_after="orders")
    assert r["status"] == "failed" and "simulated failure" in r["failure_reason"]
    for t in ("customers", "products", "orders", "orders_history", "order_items", "rejects", "run_metrics"):
        assert q(db, f"SELECT count(*) FROM {t}")[0][0] == 0, t           # atomic: nothing half-loaded
    assert q(db, "SELECT status FROM run_log")[0][0] == "failed"
    retry = run(b, db)                                                      # failed runs never block a retry
    assert retry["status"] == "success"
    assert q(db, "SELECT count(*) FROM order_items")[0][0] == 3
    assert q(db, "SELECT count(*) FROM run_log")[0][0] == 2


# ---------------------------------------------------------------- referential integrity
def test_invalid_references_and_cascade(batch, db):
    def m(d):
        d["orders"].append(["O3", "C404", "2025-03-03T10:00:00Z", "placed", "2025-03-03T10:00:00Z"])  # unknown customer
        d["order_items"].append(["I4", "O3", "P1", "1", "10.00"])       # child of rejected order
        d["order_items"].append(["I5", "O404", "P1", "1", "10.00"])     # order never delivered
        d["order_items"].append(["I6", "O1", "P404", "1", "10.00"])     # unknown product
    run(batch(mutate=m), db)
    assert reasons(db, "orders") == {"invalid_customer_ref": 1}
    assert reasons(db, "order_items") == {"parent_order_rejected": 1, "invalid_order_ref": 1, "invalid_product_ref": 1}
    assert all(c["pass"] for c in run_checks(db))


def test_child_may_reference_parent_loaded_in_earlier_batch(batch, tmp_path, db):
    run(batch("b1"), db)
    d2 = write_batch(tmp_path / "b2", {**{t: [] for t in HEADERS}, "order_items": [["I9", "O2", "P2", "1", "200.50"]]})
    assert run(d2, db)["status"] == "success"
    assert q(db, "SELECT count(*) FROM order_items")[0][0] == 4


# ---------------------------------------------------------------- domain edge cases
def test_late_arriving_older_version_does_not_overwrite_current(batch, tmp_path, db):
    run(batch("b1"), db)                                                    # O1 = completed @ 11:00
    newer = {t: [] for t in HEADERS}
    newer["orders"] = [["O1", "C1", "2025-03-01T10:00:00Z", "returned", "2025-03-05T09:00:00Z"]]
    assert run(write_batch(tmp_path / "b2", newer), db)["status"] == "success"
    assert q(db, "SELECT status FROM orders WHERE order_id='O1'")[0][0] == "returned"
    older = {t: [] for t in HEADERS}                                        # arrives LATE: a version between the two
    older["orders"] = [["O1", "C1", "2025-03-01T10:00:00Z", "shipped", "2025-03-03T09:00:00Z"]]
    r = run(write_batch(tmp_path / "b3", older), db)
    assert r["tables"]["orders"]["stale_skipped_rows"] == 1
    assert q(db, "SELECT status FROM orders WHERE order_id='O1'")[0][0] == "returned"      # current unchanged
    hist = q(db, "SELECT status FROM orders_history WHERE order_id='O1' ORDER BY updated_at")
    assert [h[0] for h in hist] == ["completed", "shipped", "returned"]                   # history preserved in order
    assert all(c["pass"] for c in run_checks(db))


def test_out_of_order_versions_within_one_file(batch, db):
    def m(d):
        d["orders"].insert(0, ["O1", "C1", "2025-03-01T10:00:00Z", "returned", "2025-03-09T00:00:00Z"])  # newer row appears first
    run(batch(mutate=m), db)
    assert q(db, "SELECT status FROM orders WHERE order_id='O1'")[0][0] == "returned"
    assert q(db, "SELECT count(*) FROM orders_history WHERE order_id='O1'")[0][0] == 2


def test_business_rule_boundaries(batch, db):
    def m(d):
        d["orders"] += [["O3", "C1", "2025-03-03T10:00:00Z", "teleported", "2025-03-03T10:00:00Z"],     # invalid status
                        ["O4", "C1", "2099-01-01T00:00:00Z", "placed", "2099-01-01T00:00:00Z"],         # future-dated
                        ["O5", "C1", "2025-12-31T23:59:59Z", "placed", "2025-12-31T23:59:59Z"]]         # boundary: just before as_of -> ok
        d["order_items"] += [["I4", "O5", "P1", "0", "10.00"], ["I5", "O5", "P1", "10001", "10.00"],     # qty out of range
                             ["I6", "O5", "P1", "1", "10.00"], ["I7", "O5", "P1", "10000", "10.00"],    # qty bounds OK
                             ["I8", "O5", "P1", "1", "-5.00"]]                                          # negative price
    run(batch(mutate=m), db)
    assert reasons(db, "orders") == {"invalid_status": 1, "future_order_ts": 1}
    assert reasons(db, "order_items") == {"invalid_quantity": 2, "invalid_unit_price": 1}
    assert q(db, "SELECT line_total FROM order_items WHERE order_item_id='I7'")[0][0] == 100000
    assert q(db, "SELECT count(*) FROM orders WHERE order_id='O5'")[0][0] == 1


def test_orders_with_same_version_twice_is_duplicate_event_not_new_version(batch, db):
    def m(d):
        d["orders"].append(list(d["orders"][0]))
    run(batch(mutate=m), db)
    assert reasons(db, "orders") == {"duplicate_key": 1}
    assert q(db, "SELECT count(*) FROM orders_history")[0][0] == 2


# ---------------------------------------------------------------- generator + labels
def test_generator_is_reproducible(tmp_path):
    generate(tmp_path / "a", tmp_path / "la", orders=600, seed=5)
    generate(tmp_path / "b", tmp_path / "lb", orders=600, seed=5)
    generate(tmp_path / "c", tmp_path / "lc", orders=600, seed=6)
    same = lambda x, y: all((tmp_path / x / f).read_bytes() == (tmp_path / y / f).read_bytes() for f in ("orders.csv", "order_items.csv", "customers.csv"))
    assert same("a", "b") and not same("a", "c")


def test_generated_data_matches_injected_labels_exactly(tmp_path, db):
    generate(tmp_path / "in", tmp_path / "labels", orders=3000, seed=11)
    r = run_pipeline(tmp_path / "in", db, as_of=AS_OF)
    assert r["status"] == "success"
    checks = run_checks(db, tmp_path / "labels" / "expected_rejects.json")
    failed = [c for c in checks if not c["pass"]]
    assert not failed, failed
    assert any("labels" in c["check"] for c in checks)
    meta = json.loads((tmp_path / "labels" / "expected_rejects.json").read_text())
    assert "expected_rejects" in meta and not (tmp_path / "in" / "expected_rejects.json").exists()   # labels kept out of inputs
