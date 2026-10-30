"""Orchestrator: ingest -> validate/stage -> (transaction) publish -> metrics.

Run lifecycle (recorded in run_log): running -> success | failed | skipped_duplicate_input.
Nothing is written to target tables until staging + validation have finished, and all target
writes happen in ONE transaction, so a failed run leaves the warehouse untouched (safe retry).
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from . import publish, validate
from .ingest import MissingInputError, SchemaError, hash_inputs, read_table, reject_id
from .schemas import DDL, TABLE_ORDER

log = logging.getLogger("yottaflex")


class InjectedFailure(Exception):
    """Used by tests/demos (--fail-after) to simulate a mid-run crash."""


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _unique_run_id(con, base):
    rid, n = base, 1
    while con.execute("SELECT 1 FROM run_log WHERE run_id = ?", [rid]).fetchone():
        n += 1
        rid = f"{base}-{n}"
    return rid


def run_pipeline(input_dir, db_path, as_of=None, force=False, fail_after=None, run_id=None, metrics_dir=None):
    input_dir, started = Path(input_dir), _now()
    as_of = as_of or started.strftime("%Y-%m-%d %H:%M:%S")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(DDL)
    in_hash = hash_inputs(input_dir)
    run_id = run_id or _unique_run_id(con, f"run_{started:%Y%m%dT%H%M%SZ}_{in_hash[:8]}")
    result = {"run_id": run_id, "input_hash": in_hash, "started_at": started.isoformat(), "as_of": as_of,
              "status": "running", "tables": {}, "warnings": [], "failure_reason": None}

    if not force and con.execute("SELECT 1 FROM run_log WHERE input_hash = ? AND status = 'success'", [in_hash]).fetchone():
        result["status"] = "skipped_duplicate_input"
        con.execute("INSERT INTO run_log (run_id, input_hash, status, started_at, ended_at, as_of, notes) VALUES (?,?,?,?,?,?,?)",
                    [run_id, in_hash, result["status"], started, _now(), as_of, "same input already loaded; use --force to reprocess"])
        log.info("[%s] input already loaded (hash %s) - skipped", run_id, in_hash[:8])
        con.close()
        return result

    con.execute("INSERT INTO run_log (run_id, input_hash, status, started_at, as_of) VALUES (?,?,?,?,?)",
                [run_id, in_hash, "running", started, as_of])
    in_txn = False
    try:
        # ---- 1. ingest (structural checks) ------------------------------------------
        reads = {}
        for t in TABLE_ORDER:
            reads[t] = read_table(input_dir / f"{t}.csv", t)
            result["warnings"] += reads[t].warnings
            log.info("[%s] read %s: %d rows, %d malformed", run_id, t, reads[t].input_rows, len(reads[t].rejects))
        # ---- 2. stage + validate (no target writes yet) ------------------------------
        for t in TABLE_ORDER:
            validate.stage(con, t, reads[t].rows, as_of)
            validate.check_references(con, t)
        # ---- 3. publish atomically ---------------------------------------------------
        con.execute("BEGIN")
        in_txn = True
        for t in TABLE_ORDER:
            m = publish.PUBLISHERS[t](con, run_id)
            total, accepted, rejected = validate.stage_counts(con, t)
            malformed = len(reads[t].rejects)
            m.update(input_rows=reads[t].input_rows, malformed_rows=malformed, rejected_rows=rejected, accepted_rows=accepted)
            result["tables"][t] = m
            con.execute("INSERT INTO run_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        [run_id, t, m["input_rows"], malformed, rejected, accepted, m["inserted_rows"], m["updated_rows"],
                         m["unchanged_rows"], m["stale_skipped_rows"], m["history_added_rows"]])
            con.execute(f"""INSERT INTO rejects SELECT '{run_id}', substr(md5('{t}|' || _source_file || '|' || _source_row), 1, 16),
                            '{t}', _source_file, _source_row, reason, _raw, ? FROM stg_{t} WHERE reason IS NOT NULL""", [_now()])
            if reads[t].rejects:
                df = pd.DataFrame([dict(run_id=run_id, reject_id=reject_id(t, r["source_file"], r["source_row"]), **r,
                                        rejected_at=_now()) for r in reads[t].rejects])
                df = df[["run_id", "reject_id", "table_name", "source_file", "source_row", "reason", "raw_record", "rejected_at"]]
                con.register("_rej", df)
                con.execute("INSERT INTO rejects SELECT * FROM _rej")
                con.unregister("_rej")
            log.info("[%s] published %s: %s", run_id, t, {k: v for k, v in m.items()})
            if fail_after == t:
                raise InjectedFailure(f"simulated failure after publishing {t}")
        publish.rebuild_rollup(con)
        con.execute("COMMIT")
        in_txn = False
        result["status"] = "success"
    except (SchemaError, MissingInputError, InjectedFailure, duckdb.Error, OSError) as e:
        if in_txn:
            con.execute("ROLLBACK")
        result["status"], result["failure_reason"] = "failed", f"{type(e).__name__}: {e}"
        log.error("[%s] FAILED: %s", run_id, result["failure_reason"])
    except Exception as e:  # unexpected: still record it, then re-raise
        if in_txn:
            con.execute("ROLLBACK")
        con.execute("UPDATE run_log SET status='failed', ended_at=?, failure_reason=? WHERE run_id=?",
                    [_now(), f"{type(e).__name__}: {e}", run_id])
        con.close()
        raise

    ended = _now()
    tot = result["tables"].values()
    inp, acc = sum(m["input_rows"] for m in tot), sum(m["accepted_rows"] for m in tot)
    rej = sum(m["rejected_rows"] + m["malformed_rows"] for m in tot) if result["status"] == "success" else None
    con.execute("UPDATE run_log SET status=?, ended_at=?, input_rows=?, accepted_rows=?, rejected_rows=?, failure_reason=?, notes=? WHERE run_id=?",
                [result["status"], ended, inp if result["status"] == "success" else None, acc if result["status"] == "success" else None,
                 rej, result["failure_reason"], "; ".join(result["warnings"]) or None, run_id])
    result["ended_at"] = ended.isoformat()
    result["duration_s"] = round((ended - started).total_seconds(), 3)
    if metrics_dir:
        Path(metrics_dir).mkdir(parents=True, exist_ok=True)
        (Path(metrics_dir) / f"{run_id}.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    log.info("[%s] %s in %.2fs", run_id, result["status"], result["duration_s"])
    con.close()
    return result
