"""Validated rows -> silver, idempotently (ON CONFLICT upserts) and in ONE transaction. Also the entry point for
tables landed by Airbyte (integrations/airbyte/generic.py builds canonical rows and calls `import_rows`)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..db import upsert
from . import parse, validate
from .coerce import slug
from .spec import KINDS, norm

Conn = psycopg.Connection[Any]
PIPELINE_ID, PIPELINE_LABEL = "upload", "Importado"
ID_PREFIX = "up:"


@dataclass
class ImportOptions:
    dry_run: bool = True
    allow_partial: bool = False
    replace: bool = False
    import_notes: bool = True
    stage_order: list[str] | None = None
    uploaded_by: str | None = None
    source: str = "up"  # id prefix: `up:` for uploads, or an Airbyte source name


@dataclass
class ImportResult:
    report: validate.Report
    upload_id: str | None = None
    imported: dict[str, int] = field(default_factory=dict)
    status: str = "validated"

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "upload_id": self.upload_id, "imported": self.imported, "report": self.report.to_dict()}


def _resolve_owners(conn: Conn, names: set[str], prefix: str = ID_PREFIX) -> dict[str, str]:
    """Owner cell -> hs_owner_id. Existing ids win, then existing full names (so uploads line up with HubSpot owners), else up:<slug>."""
    with conn.cursor() as cur:
        cur.execute("select hs_owner_id, coalesce(first_name,'') || ' ' || coalesce(last_name,'') as full from silver.owner")
        rows = cur.fetchall()
    by_id = {r["hs_owner_id"] for r in rows}
    by_name = {norm(r["full"]): r["hs_owner_id"] for r in rows if r["full"].strip()}
    out: dict[str, str] = {}
    new: list[dict[str, Any]] = []
    for n in names:
        if n in by_id:
            out[n] = n
        elif norm(n) in by_name:
            out[n] = by_name[norm(n)]
        else:
            oid = f"{prefix}{slug(n)}"
            out[n] = oid
            first, _, last = n.partition(" ")
            new.append({"hs_owner_id": oid, "email": None, "first_name": first, "last_name": last or None, "is_active": True})
    upsert(conn, "silver.owner", new, ["hs_owner_id"])
    return out


def _import_deals(conn: Conn, rows: list[dict[str, Any]], stage_order: list[str], opts: ImportOptions) -> dict[str, int]:
    now = datetime.now(UTC)
    prefix = f"{opts.source}:"
    pipeline_id = PIPELINE_ID if opts.source == "up" else opts.source
    pipeline_label = PIPELINE_LABEL if opts.source == "up" else f"Airbyte: {opts.source}"
    if opts.replace:
        with conn.cursor() as cur:
            cur.execute("delete from silver.activity where hs_deal_id like %s", (f"{prefix}%",))
            cur.execute("delete from silver.deal where hs_deal_id like %s", (f"{prefix}%",))
    upsert(conn, "silver.pipeline", [{"hs_pipeline_id": pipeline_id, "label": pipeline_label}], ["hs_pipeline_id"])
    n = len(stage_order)
    stages = [{"hs_pipeline_id": pipeline_id, "hs_stage_id": f"{prefix}{slug(s)}", "label": s, "display_order": i,
               "is_closed": False, "probability": Decimal(str(round(0.1 + (0.8 * i / max(1, n - 1) if n > 1 else 0.3), 3)))}
              for i, s in enumerate(stage_order)]
    stages += [{"hs_pipeline_id": pipeline_id, "hs_stage_id": f"{prefix}won", "label": "Fechado ganho", "display_order": n,
                "is_closed": True, "probability": Decimal("1.000")},
               {"hs_pipeline_id": pipeline_id, "hs_stage_id": f"{prefix}lost", "label": "Fechado perdido", "display_order": n + 1,
                "is_closed": True, "probability": Decimal("0.000")}]
    upsert(conn, "silver.stage", stages, ["hs_pipeline_id", "hs_stage_id"])
    owners = _resolve_owners(conn, {r["owner"] for r in rows if r["owner"]}, prefix)
    deals, acts = [], []
    for r in rows:
        did = f"{prefix}{r['id']}"
        st = r["status"]
        stage_id = f"{prefix}{'won' if st == 'won' else 'lost' if st == 'lost' else slug(r['stage'])}"
        closed = st in ("won", "lost")
        deals.append({
            "hs_deal_id": did, "name": r["name"], "amount": r["amount"], "currency": "BRL", "hs_pipeline_id": pipeline_id,
            "hs_stage_id": stage_id, "hs_owner_id": owners.get(r["owner"]) if r["owner"] else None, "created_at": r["created_at"],
            "close_date": r["close_date"], "closed_at": r["close_date"] if closed else None, "is_open": not closed,
            "is_won": st == "won", "is_lost": st == "lost", "lost_reason_hs": r["lost_reason"], "source": r["campaign"],
            "last_activity_at": None, "next_activity_at": r["next_activity"], "num_contacts": 0, "close_date_pushes": 0,
            "hs_updated_at": now, "is_archived": False})
        if r["next_activity"] and not closed:  # a real open task, so "next step missing" is computed from data instead of guessed
            acts.append(_act(f"task:{did}", "task", did, None, r["next_activity"], summary="Próxima atividade (importada)", is_completed=False, due=r["next_activity"], now=now))
        if opts.import_notes:
            ids = r["note_ids"] or [f"{r['id']}-{i + 1}" for i in range(len(r["notes"]))]
            for nid, text in zip(ids, r["notes"], strict=False):
                acts.append(_act(f"note:{prefix}{nid}", "note", did, None, None, summary=text[:500], is_completed=None, due=None, now=now))
    upsert(conn, "silver.deal", deals, ["hs_deal_id"])
    upsert(conn, "silver.activity", acts, ["hs_activity_id"])
    return {"deals": len(deals), "activities": len(acts), "owners": len(owners), "stages": len(stages)}


def _act(aid: str, kind: str, deal: str, owner: str | None, occurred: datetime | None, *, summary: str, is_completed: bool | None,
         due: datetime | None, now: datetime) -> dict[str, Any]:
    return {"hs_activity_id": aid, "activity_type": kind, "hs_deal_id": deal, "hs_contact_id": None, "hs_owner_id": owner,
            "occurred_at": occurred, "due_at": due, "is_completed": is_completed, "duration_sec": None, "direction": None,
            "outcome": None, "summary": summary, "transcript_path": None, "hs_updated_at": now}


def _import_quotas(conn: Conn, rows: list[dict[str, Any]]) -> dict[str, int]:
    owners = _resolve_owners(conn, {r["owner"] for r in rows})
    upsert(conn, "silver.quota", [{"hs_owner_id": owners[r["owner"]], "period_start": r["period_start"], "period_end": r["period_end"],
                                   "amount": r["amount"], "source": "upload"} for r in rows], ["hs_owner_id", "period_start", "period_end"])
    return {"quotas": len(rows), "owners": len(owners)}


def _record(conn: Conn, rep: validate.Report, opts: ImportOptions, status: str, imported: int) -> str:
    with conn.cursor() as cur:
        cur.execute("insert into app.dataset_upload (kind, filename, sha256, size_bytes, status, total_rows, imported_rows, error_count, options, errors, summary, "
                    "uploaded_by, imported_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                    (rep.kind, rep.filename[:200], rep.sha256, rep.size_bytes, status, rep.total_rows, imported, rep.error_count,
                     Jsonb({"allow_partial": opts.allow_partial, "replace": opts.replace, "import_notes": opts.import_notes,
                            "stage_order": opts.stage_order}),
                     Jsonb([{"line": e.line, "column": e.column, "message": e.message} for e in rep.errors[:50]]),
                     Jsonb(rep.summary), opts.uploaded_by, datetime.now(UTC) if status == "imported" else None))
        return str(cur.fetchone()["id"])  # type: ignore[index]


def import_rows(conn: Conn, kind: str, rep: validate.Report, rows: list[dict[str, Any]], opts: ImportOptions) -> ImportResult:
    """Apply already-validated rows. Refuses when there are errors unless allow_partial. Commits once or not at all."""
    res = ImportResult(rep)
    blocked = bool(rep.missing_required) or (rep.error_count > 0 and not opts.allow_partial) or not rows
    if opts.dry_run or blocked:
        res.status = "validated" if not blocked else "rejected"
        if not opts.dry_run:  # only real attempts leave an audit row
            res.upload_id = _record(conn, rep, opts, "rejected", 0)
            conn.commit()
        return res
    try:
        res.imported = _import_deals(conn, rows, rep.stage_order, opts) if kind == "deals" else _import_quotas(conn, rows)
        res.upload_id = _record(conn, rep, opts, "imported", len(rows))
        conn.commit()
        res.status = "imported"
    except Exception:
        conn.rollback()
        res.upload_id = _record(conn, rep, opts, "failed", 0)
        conn.commit()
        res.status = "failed"
        raise
    return res


def import_file(conn: Conn, kind: str, data: bytes, filename: str, opts: ImportOptions, *, max_bytes: int = 10_000_000,
                max_rows: int = 100_000) -> ImportResult:
    """File bytes -> report (+ import unless dry_run). Raises parse.UploadError for whole-file problems."""
    spec = KINDS[kind]
    table = parse.read_table(data, filename, max_bytes=max_bytes, max_rows=max_rows)
    rep, rows = validate.validate(spec, table, filename, data, stage_order=opts.stage_order)
    return import_rows(conn, kind, rep, rows, opts)


