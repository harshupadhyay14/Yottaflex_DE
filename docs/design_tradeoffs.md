# Design & trade-off note

**Why DuckDB + SQL for validation.** Rules are declarative, set-based and fast (828k rows end-to-end in ~7 s); `TRY_CAST` turns every bad value into a reject instead of an exception. Python is used only for structural CSV checks, where row numbers and raw records must be preserved.

**One reason per rejected row.** Ordered checks (required -> format -> rule -> duplicate -> reference) keep rejects countable and make reconciliation exact: `input = accepted + rejected + malformed`. Trade-off: a row with several defects only reports the first.

**Atomic load over per-table commits.** All target writes, rejects and metrics are one transaction; a crash leaves nothing half-loaded and retry is trivial. Trade-off: one big transaction; at much larger scale you'd partition batches (by file/date) and commit per partition.

**Upsert via DELETE+INSERT, no enforced PKs.** DuckDB rejects delete+insert of the same key inside one transaction when a PK index exists. Keys are therefore guaranteed by dedupe in staging and verified by `reconcile`. In a warehouse with `MERGE` the same logic maps directly.

**History for orders, overwrite for dimensions.** Orders change state and the task asks not to silently overwrite history, so each version is appended to `orders_history`, and `orders` only moves forward in `updated_at`. This also makes late/out-of-order arrival safe. Customers/products are Type-1 (overwrite) to keep scope small; SCD2 is the documented next step.

**Run-level + row-level idempotency.** The input hash short-circuits identical reruns (cheap, and visible in `run_log`); row-level upserts guarantee that even `--force` or overlapping backfills converge.

**Cascade reason `parent_order_rejected`.** Distinguishes "order was delivered but rejected" from "order never delivered" (`invalid_order_ref`), which is what an operator needs to triage.

**Benchmark honesty.** Baseline queries are deliberately naive but semantically identical to the optimised ones (results compared). The rollup wins big; the other two optimisations are modest, and the report says so. Timings are warm-cache medians on one machine; use ratios, not absolutes.

**Not done (by design):** streaming ingestion, SCD2 dimensions, incremental rollup, auth/secrets (none needed: all data synthetic, no credentials).
