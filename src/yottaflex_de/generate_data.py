"""Seeded synthetic data generator with deliberately injected, *labelled* defects.

Inputs (CSV) go to --out. The expected-answer labels (how many rows of each defect were
injected) go to a SEPARATE directory (--labels) so they never mix with input data.
Each injected row carries exactly one defect, so label counts map 1:1 to reject reasons.
"""
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

COUNTRIES = ["IN", "US", "GB", "DE", "FR", "SG", "AE", "AU", "CA", "BR"]
CATEGORIES = ["audio", "video", "accessories", "storage", "wearables", "networking"]
STATUS_W = [("placed", 10), ("paid", 15), ("shipped", 15), ("completed", 50), ("cancelled", 7), ("returned", 3)]
BAD_QTY = ["0", "-3", "abc", "10001", ""]  # "" -> missing_quantity, others -> invalid_quantity


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _take(rng, pool, rate, n):
    """Remove and return a random subset of `pool` (keeps injected sets disjoint)."""
    k = min(len(pool), max(1, round(n * rate)))
    chosen = rng.sample(pool, k)
    s = set(chosen)
    pool[:] = [x for x in pool if x not in s]
    return sorted(chosen)


def _write(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def generate(out_dir, labels_dir, orders=1000, seed=42):
    rng = random.Random(seed)
    out, lab = Path(out_dir), Path(labels_dir)
    out.mkdir(parents=True, exist_ok=True)
    lab.mkdir(parents=True, exist_ok=True)
    labels = {t: {} for t in ("customers", "products", "orders", "order_items")}
    n_cust, n_prod = max(orders // 10, 30), max(orders // 200, 20)

    # ---- customers -------------------------------------------------------------------
    cust = []
    base = datetime(2023, 1, 1)
    for i in range(n_cust):
        cust.append([f"C{i:06d}", f"Customer {i}", f"user{i}@example.com", rng.choice(COUNTRIES),
                     _ts(base + timedelta(seconds=rng.randint(0, 700 * 86400)))])
    pool = list(range(n_cust))
    bad_email, bad_country, dup_c = _take(rng, pool, .01, n_cust), _take(rng, pool, .01, n_cust), _take(rng, pool, .02, n_cust)
    for i in bad_email:
        cust[i][2] = ""
    for i in bad_country:
        cust[i][3] = "India"
    bad_c = set(bad_email) | set(bad_country)
    good_cust = [cust[i][0] for i in range(n_cust) if i not in bad_c]
    cust_rows = cust + [list(cust[i]) for i in dup_c]
    labels["customers"] = {"missing_email": len(bad_email), "invalid_country": len(bad_country), "duplicate_key": len(dup_c)}
    n_c = _write(out / "customers.csv", ["customer_id", "name", "email", "country", "signup_ts"], cust_rows)

    # ---- products --------------------------------------------------------------------
    prod = []
    for i in range(n_prod):
        prod.append([f"P{i:05d}", f"Product {i}", rng.choice(CATEGORIES), f"{rng.uniform(5, 500):.2f}"])
    pool = list(range(n_prod))
    bad_cat, bad_price, dup_p = _take(rng, pool, .01, n_prod), _take(rng, pool, .01, n_prod), _take(rng, pool, .02, n_prod)
    for i in bad_cat:
        prod[i][2] = ""
    for i in bad_price:
        prod[i][3] = "-1.00"
    bad_p = set(bad_cat) | set(bad_price)
    good_prod = [prod[i] for i in range(n_prod) if i not in bad_p]
    prod_rows = prod + [list(prod[i]) for i in dup_p]
    labels["products"] = {"missing_category": len(bad_cat), "invalid_unit_price": len(bad_price), "duplicate_key": len(dup_p)}
    n_p = _write(out / "products.csv", ["product_id", "name", "category", "unit_price"], prod_rows)

    # ---- orders ----------------------------------------------------------------------
    start = datetime(2025, 1, 1)
    base_orders = []
    for i in range(orders):
        ots = start + timedelta(seconds=rng.randint(0, 355 * 86400))
        status = rng.choices([s for s, _ in STATUS_W], [w for _, w in STATUS_W])[0]
        base_orders.append([f"O{i:07d}", rng.choice(good_cust), _ts(ots), status, _ts(ots + timedelta(minutes=rng.randint(1, 600)))])
    pool = list(range(orders))
    s_status, s_future, s_ts = _take(rng, pool, .003, orders), _take(rng, pool, .002, orders), _take(rng, pool, .002, orders)
    s_ref, s_nocust, s_mal = _take(rng, pool, .005, orders), _take(rng, pool, .002, orders), _take(rng, pool, .002, orders)
    s_dup, s_upd = _take(rng, pool, .005, orders), _take(rng, pool, .02, orders)
    for i in s_status:
        base_orders[i][3] = "teleported"
    for i in s_future:
        base_orders[i][2] = "2099-01-01T00:00:00Z"
    for i in s_ts:
        base_orders[i][2] = "2025-13-45T99:00:00Z"
    for i in s_ref:
        base_orders[i][1] = "C999999"
    for i in s_nocust:
        base_orders[i][1] = ""
    rejected_orders = set(s_status) | set(s_future) | set(s_ts) | set(s_ref) | set(s_nocust)
    malformed_orders = set(s_mal)
    upd_set = set(s_upd)
    order_rows = []
    for i, row in enumerate(base_orders):
        v2 = None
        if i in upd_set:
            u = datetime.strptime(row[4], "%Y-%m-%dT%H:%M:%SZ") + timedelta(days=rng.randint(1, 5))
            v2 = [row[0], row[1], row[2], "returned" if row[3] == "completed" else "completed", _ts(u)]
        if i in malformed_orders:
            order_rows.append(row + ["junk"])
        elif v2 and i % 2 == 0:
            order_rows += [v2, row]            # newer version arrives BEFORE older one (out of order)
        elif v2:
            order_rows += [row, v2]
        else:
            order_rows.append(row)
    order_rows += [list(base_orders[i]) for i in s_dup]
    labels["orders"] = {"invalid_status": len(s_status), "future_order_ts": len(s_future), "invalid_order_ts": len(s_ts),
                        "invalid_customer_ref": len(s_ref), "missing_customer_id": len(s_nocust),
                        "malformed_row_field_count": len(s_mal), "duplicate_key": len(s_dup)}
    n_o = _write(out / "orders.csv", ["order_id", "customer_id", "order_ts", "status", "updated_at"], order_rows)

    # ---- order items -----------------------------------------------------------------
    items, parent_rej, orphan = [], 0, 0
    ok_item_idx = []
    n = 0
    for i, o in enumerate(base_orders):
        for _ in range(rng.randint(1, 5)):
            p = rng.choice(good_prod)
            items.append([f"I{n:08d}", o[0], p[0], str(rng.randint(1, 5)), p[3]])
            if i in rejected_orders:
                parent_rej += 1
            elif i in malformed_orders:
                orphan += 1
            else:
                ok_item_idx.append(len(items) - 1)
            n += 1
    m = len(ok_item_idx)
    pool = list(range(len(ok_item_idx)))
    s_q, s_pref, s_imal, s_idup = _take(rng, pool, .003, m), _take(rng, pool, .003, m), _take(rng, pool, .001, m), _take(rng, pool, .003, m)
    ok = [ok_item_idx[j] for j in range(m)]
    q_missing = q_invalid = 0
    for k, j in enumerate(s_q):
        v = BAD_QTY[k % len(BAD_QTY)]
        items[ok[j]][3] = v
        q_missing += v == ""
        q_invalid += v != ""
    for j in s_pref:
        items[ok[j]][2] = "P99999"
    item_rows = []
    mal_idx = {ok[j] for j in s_imal}
    for idx, r in enumerate(items):
        item_rows.append(r[:-1] if idx in mal_idx else r)
    item_rows += [list(items[ok[j]]) for j in s_idup]
    labels["order_items"] = {"missing_quantity": q_missing, "invalid_quantity": q_invalid, "invalid_product_ref": len(s_pref),
                             "parent_order_rejected": parent_rej, "invalid_order_ref": orphan,
                             "malformed_row_field_count": len(s_imal), "duplicate_key": len(s_idup)}
    n_i = _write(out / "order_items.csv", ["order_item_id", "order_id", "product_id", "quantity", "unit_price"], item_rows)

    meta = {"seed": seed, "orders_requested": orders,
            "input_rows": {"customers": n_c, "products": n_p, "orders": n_o, "order_items": n_i},
            "expected_rejects": {t: {k: v for k, v in d.items() if v} for t, d in labels.items()},
            "orders_updated_in_source": len(s_upd)}
    (lab / "expected_rejects.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    return meta
