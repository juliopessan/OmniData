"""Any Airbyte-landed table -> canonical dataset (deals/quotas) via a column mapping in config/integrations.yaml.
Goes through the SAME validation and importer as CSV uploads, so every source gets identical guarantees."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
import yaml
from psycopg import sql

from ...config import ROOT
from ...datasets import importer, validate
from ...datasets.parse import Table
from ...datasets.spec import KINDS
from .landing import IDENT

Conn = psycopg.Connection[Any]


def load_config() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / "config" / "integrations.yaml").read_text()) or {}
    return data


def _s(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return str(v).strip()


def _check(spec: dict[str, Any]) -> tuple[str, str, dict[str, str]]:
    kind = spec.get("kind")
    schema, _, table = str(spec.get("table", "")).partition(".")
    cols: dict[str, str] = spec.get("columns") or {}
    if kind not in KINDS or not IDENT.match(schema) or not IDENT.match(table) or not IDENT.match(str(spec.get("name", "x")).replace("-", "_")):
        raise ValueError(f"invalid generic mapping: {spec.get('name')}")
    known = {c.name for c in KINDS[kind].columns}
    bad = [k for k in cols if k not in known] + [v for v in cols.values() if not IDENT.match(str(v))]
    if bad:
        raise ValueError(f"invalid columns in mapping {spec['name']}: {bad}")
    return schema, table, cols


def read_table(conn: Conn, spec: dict[str, Any], max_rows: int = 100_000) -> Table:
    schema, table, cols = _check(spec)
    q = sql.SQL("select {cols} from {t} limit {n}").format(
        cols=sql.SQL(", ").join(sql.SQL("{} as {}").format(sql.Identifier(src), sql.Identifier(canon)) for canon, src in cols.items()),
        t=sql.SQL(".").join((sql.Identifier(schema), sql.Identifier(table))), n=sql.Literal(max_rows + 1))
    with conn.cursor() as cur:
        cur.execute(q)
        raw = cur.fetchall()
    if len(raw) > max_rows:
        raise ValueError(f"{spec['name']}: more than {max_rows} rows; raise DATASET_MAX_ROWS")
    smap = {str(k).lower(): str(v) for k, v in (spec.get("status_map") or {}).items()}
    headers = list(cols)
    rows = []
    for r in raw:
        cells = [_s(r[c]) for c in headers]
        if "status" in headers:
            i = headers.index("status")
            cells[i] = smap.get(cells[i].lower(), cells[i])
        rows.append(cells)
    return Table(headers, rows, list(range(2, len(rows) + 2)), "postgres", None)


def run_one(conn: Conn, spec: dict[str, Any], *, apply: bool, max_rows: int = 100_000) -> importer.ImportResult:
    table = read_table(conn, spec, max_rows)
    kind = spec["kind"]
    rep, rows = validate.validate(KINDS[kind], table, f"airbyte:{spec['name']}", repr(spec).encode(), stage_order=spec.get("stage_order"))
    opts = importer.ImportOptions(dry_run=not apply, allow_partial=bool(spec.get("allow_partial", False)), replace=bool(spec.get("replace", True)),
                                  import_notes=bool(spec.get("import_notes", False)), source=str(spec["name"]).replace("_", "-"),
                                  uploaded_by=f"airbyte:{spec['name']}")
    return importer.import_rows(conn, kind, rep, rows, opts)


def run_all(conn: Conn, *, apply: bool, only: str | None = None, max_rows: int = 100_000) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in load_config().get("generic", []):
        if only and spec.get("name") != only:
            continue
        if not spec.get("enabled") and spec.get("name") != only:
            out[spec["name"]] = "disabled"
            continue
        res = run_one(conn, spec, apply=apply, max_rows=max_rows)
        out[spec["name"]] = {"status": res.status, "valid_rows": res.report.valid_rows, "errors": res.report.error_count}
    return out
