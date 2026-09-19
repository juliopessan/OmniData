"""Airbyte -> silver. Airbyte's Postgres destination lands each HubSpot stream as a table (quoted, case-preserved columns,
properties flattened as `properties_<name>`, associations as JSONB arrays). We rebuild HubSpot-shaped objects from those rows and
reuse crm/hubspot/mapping.py, so direct ingestion and Airbyte ingestion produce identical silver rows.
Shapes verified against airbyte/airbyte source-hubspot 6.9.2 (manifest.yaml): pipelineId/stageId, stages[].metadata.{isClosed,probability},
deals_property_history{dealId,property,timestamp,value}, engagements_*{deals,contacts,companies arrays}."""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import sql

from ...crm.hubspot import mapping as m
from ...db import upsert

Conn = psycopg.Connection[Any]
PINNED_SOURCE = "airbyte/source-hubspot 6.9.2"
CHUNK = 1000
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EXTRACTED = "_airbyte_extracted_at"
RAW_ID = "_airbyte_raw_id"  # present in every Airbyte final table; the only universal tiebreaker (deal_pipelines has no `id`)
STREAMS = ["owners", "deal_pipelines", "contacts", "companies", "deals", "deals_property_history",
           "engagements_notes", "engagements_tasks", "engagements_calls", "engagements_meetings", "engagements_emails"]
ACTIVITY_STREAMS = {"engagements_notes": "notes", "engagements_tasks": "tasks", "engagements_calls": "calls",
                    "engagements_meetings": "meetings", "engagements_emails": "emails"}


def _ident(schema: str, table: str) -> sql.Composed:
    if not IDENT.match(schema) or not IDENT.match(table):
        raise ValueError("invalid schema/table name")
    return sql.SQL(".").join((sql.Identifier(schema), sql.Identifier(table)))


def table_exists(conn: Conn, schema: str, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select 1 from information_schema.tables where table_schema=%s and table_name=%s", (schema, table))
        return cur.fetchone() is not None


def iter_rows(conn: Conn, schema: str, table: str, after: datetime | None) -> Iterator[list[dict[str, Any]]]:
    """Keyset pagination on (_airbyte_extracted_at, _airbyte_raw_id): stable, resumable, bounded memory. Keys are lower-cased."""
    last_ts, last_id = after, ""
    while True:
        where = sql.SQL("where ({t}, {i}) > (%s, %s)").format(t=sql.Identifier(EXTRACTED), i=sql.Identifier(RAW_ID)) if last_ts else sql.SQL("")
        q = sql.SQL("select * from {tbl} {w} order by {t}, {i} limit {n}").format(
            tbl=_ident(schema, table), w=where, t=sql.Identifier(EXTRACTED), i=sql.Identifier(RAW_ID), n=sql.Literal(CHUNK))
        with conn.cursor() as cur:
            cur.execute(q, [last_ts, last_id] if last_ts else None)
            raw = cur.fetchall()
        if not raw:
            return
        rows = [{k.lower(): v for k, v in r.items()} for r in raw]
        yield rows
        last_ts, last_id = rows[-1][EXTRACTED], str(rows[-1][RAW_ID])
        if len(raw) < CHUNK:
            return


def hs_shape(row: dict[str, Any]) -> dict[str, Any]:
    """Airbyte row -> the object shape the HubSpot API returns."""
    props = {k[len("properties_"):]: v for k, v in row.items() if k.startswith("properties_")}
    props.setdefault("createdate", row.get("createdat"))
    props.setdefault("hs_lastmodifieddate", row.get("updatedat") or row.get(EXTRACTED))
    return {"id": row["id"], "archived": bool(row.get("archived")), "properties": props}


def _ids(v: Any) -> list[str]:
    return [str(x["id"] if isinstance(x, dict) else x) for x in (v or [])]


def _cursor(conn: Conn, stream: str) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("select high_watermark from app.ingest_cursor where object_type=%s", (f"airbyte:{stream}",))
        r = cur.fetchone()
    return r["high_watermark"] if r else None


def _save_cursor(conn: Conn, stream: str, ts: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into app.ingest_cursor (object_type, high_watermark) values (%s,%s) on conflict (object_type) do update "
                    "set high_watermark=excluded.high_watermark, updated_at=now()", (f"airbyte:{stream}", ts))


def _stage_flags(conn: Conn) -> dict[tuple[str, str], tuple[bool, Decimal | None]]:
    with conn.cursor() as cur:
        cur.execute("select hs_pipeline_id, hs_stage_id, is_closed, probability from silver.stage")
        return {(r["hs_pipeline_id"], r["hs_stage_id"]): (r["is_closed"], r["probability"]) for r in cur.fetchall()}


# ---- one handler per stream: rows -> silver -------------------------------------------------------
def _owners(conn: Conn, rows: list[dict[str, Any]]) -> None:
    upsert(conn, "silver.owner", [m.map_owner({"id": r["id"], "email": r.get("email"), "firstName": r.get("firstname"),
                                                "lastName": r.get("lastname"), "archived": r.get("archived")}) for r in rows], ["hs_owner_id"])


def _pipelines(conn: Conn, rows: list[dict[str, Any]]) -> None:
    for r in rows:
        stages = [{"id": s.get("stageId") or s.get("id"), "label": s.get("label"), "displayOrder": s.get("displayOrder"),
                   "metadata": s.get("metadata") or {}} for s in (r.get("stages") or [])]
        pipe, st = m.map_pipeline({"id": r["pipelineid"], "label": r["label"], "stages": stages})
        upsert(conn, "silver.pipeline", [pipe], ["hs_pipeline_id"])
        upsert(conn, "silver.stage", st, ["hs_pipeline_id", "hs_stage_id"])


def _contacts(conn: Conn, rows: list[dict[str, Any]]) -> None:
    upsert(conn, "silver.contact", [m.map_contact(hs_shape(r)) for r in rows], ["hs_contact_id"])


def _companies(conn: Conn, rows: list[dict[str, Any]]) -> None:
    upsert(conn, "silver.company", [m.map_company(hs_shape(r)) for r in rows], ["hs_company_id"])


def _deals(conn: Conn, rows: list[dict[str, Any]]) -> None:
    flags = _stage_flags(conn)
    upsert(conn, "silver.deal", [m.map_deal(hs_shape(r), flags) for r in rows], ["hs_deal_id"])
    for key, table, col in (("contacts", "silver.deal_contact", "hs_contact_id"), ("companies", "silver.deal_company", "hs_company_id")):
        upsert(conn, table, [{"hs_deal_id": str(r["id"]), col: t} for r in rows for t in _ids(r.get(key))], ["hs_deal_id", col])


def _history(conn: Conn, rows: list[dict[str, Any]]) -> None:
    """deals_property_history rows -> stage timeline, property changes and close-date pushes (same functions as direct ingestion)."""
    by: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[str(r["dealid"])][r["property"]].append({"timestamp": r["timestamp"], "value": r.get("value")})
    flags = _stage_flags(conn)
    stage_to_pipeline = {s: p for (p, s) in flags}
    stages, changes, pushes = [], [], []
    for did, props in by.items():
        stages += m.stage_history(did, props.get("dealstage", []), stage_to_pipeline)
        for prop in ("dealstage", "amount", "closedate", "hubspot_owner_id"):
            changes += m.property_changes(did, prop, props.get(prop, []))
        if "closedate" in props:
            pushes.append((m.close_date_pushes(props["closedate"]), did))
    upsert(conn, "silver.deal_stage_history", stages, ["hs_deal_id", "hs_stage_id", "entered_at"])
    upsert(conn, "silver.deal_property_change", changes, ["hs_deal_id", "property", "changed_at"])
    with conn.cursor() as cur:
        cur.executemany("update silver.deal set close_date_pushes=%s where hs_deal_id=%s", pushes)


def _activities(conn: Conn, stream: str, rows: list[dict[str, Any]]) -> None:
    otype = ACTIVITY_STREAMS[stream]
    out = []
    for r in rows:
        a = m.map_activity(otype, hs_shape(r))
        deals, contacts = _ids(r.get("deals")), _ids(r.get("contacts"))
        a["hs_deal_id"], a["hs_contact_id"] = (deals[0] if deals else None), (contacts[0] if contacts else None)
        out.append(a)
    upsert(conn, "silver.activity", out, ["hs_activity_id"])


HANDLERS = {"owners": _owners, "deal_pipelines": _pipelines, "contacts": _contacts, "companies": _companies,
            "deals": _deals, "deals_property_history": _history}


def ingest(conn: Conn, schema: str = "airbyte", *, streams: list[str] | None = None, full: bool = False) -> dict[str, int | str]:
    """Process every landed HubSpot stream newer than its cursor. Each chunk + cursor commit together (safe to kill and re-run)."""
    result: dict[str, int | str] = {}
    for stream in [s for s in STREAMS if not streams or s in streams]:
        if not table_exists(conn, schema, stream):
            result[stream] = "skipped: table not found (stream not enabled in Airbyte?)"
            continue
        after = None if full else _cursor(conn, stream)
        n = 0
        for chunk in iter_rows(conn, schema, stream, after):
            if stream in ACTIVITY_STREAMS:
                _activities(conn, stream, chunk)
            else:
                HANDLERS[stream](conn, chunk)
            ts = chunk[-1][EXTRACTED]
            _save_cursor(conn, stream, ts if ts.tzinfo else ts.replace(tzinfo=UTC))
            conn.commit()
            n += len(chunk)
        result[stream] = n
    return result
