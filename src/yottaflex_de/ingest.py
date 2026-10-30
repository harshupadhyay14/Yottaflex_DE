"""CSV ingestion: header/schema checks and row-level structural rejects.

Everything is read as text. Typing and business rules are applied later in SQL (validate.py),
so a malformed value can never crash the load - it becomes a traceable reject instead.
"""
import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .schemas import SCHEMAS


class SchemaError(Exception):
    """Header is missing a required column (unexpected schema change)."""


class MissingInputError(Exception):
    """An expected input file was not delivered."""


@dataclass
class ReadResult:
    rows: list = field(default_factory=list)       # tuples: schema cols..., source_file, source_row, raw_json
    rejects: list = field(default_factory=list)    # structural rejects (never reach SQL staging)
    warnings: list = field(default_factory=list)
    input_rows: int = 0


def reject_id(table, source_file, source_row):
    return hashlib.md5(f"{table}|{source_file}|{source_row}".encode()).hexdigest()[:16]


def hash_inputs(input_dir: Path, tables=SCHEMAS) -> str:
    h = hashlib.sha256()
    for t in tables:
        p = Path(input_dir) / f"{t}.csv"
        h.update(t.encode())
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def read_table(path: Path, table: str) -> ReadResult:
    cols = SCHEMAS[table]
    names = [c.name for c in cols]
    res = ReadResult()
    if not path.exists():
        raise MissingInputError(f"missing_input_file: {path.name}")
    src = path.name
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = [h.strip().lower() for h in next(reader)]
        except StopIteration:
            return res                                   # zero-byte file == empty batch
        missing = [c.name for c in cols if c.required and c.name not in header]
        if missing:
            raise SchemaError(f"schema_change: {path.name} missing required column(s) {missing}; header={header}")
        unknown = [h for h in header if h not in names]
        absent_optional = [c.name for c in cols if not c.required and c.name not in header]
        if unknown:
            res.warnings.append(f"{path.name}: ignoring unknown column(s) {unknown}")
        if absent_optional:
            res.warnings.append(f"{path.name}: optional column(s) absent {absent_optional}; filled with NULL")
        idx = {n: header.index(n) for n in names if n in header}
        while True:
            try:
                rec = next(reader)
            except StopIteration:
                break
            except csv.Error as e:                       # unparsable line
                res.input_rows += 1
                res.rejects.append(dict(table_name=table, source_file=src, source_row=reader.line_num,
                                        reason="malformed_row_parse_error", raw_record=str(e)))
                continue
            if not rec:                                  # blank line: ignore
                continue
            res.input_rows += 1
            line = reader.line_num
            if len(rec) != len(header):
                res.rejects.append(dict(table_name=table, source_file=src, source_row=line,
                                        reason="malformed_row_field_count", raw_record=json.dumps(rec)))
                continue
            vals = tuple((rec[idx[n]].strip() or None) if n in idx else None for n in names)
            res.rows.append(vals + (src, line, json.dumps(rec)))
    return res
