"""Backfill, incremental sync and weekly snapshots (FR-ING-1, 2, 4). All writes are idempotent upserts."""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..config import hubspot_properties
from ..crm.hubspot import mapping as m
from ..crm.hubspot.client import HubSpotClient
from ..db import upsert

log = logging.getLogger("omnidata.ingest")
OBJECT_ORDER = ["contacts", "companies", "deals", "calls", "meetings", "emails", "notes", "tasks"]
INCREMENTAL_OVERLAP = timedelta(minutes=5)  # re-read a small tail so clock skew cannot drop rows
Conn = psycopg.Connection[Any]


# ---- metadata -----------------------------------------------------------------
async def sync_metadata(conn: Conn, client: HubSpotClient) -> None:
    upsert(conn, "silver.owner", [m.map_owner(o) for o in await client.owners()], ["hs_owner_id"])
    for p in await client.pipelines("deals"):
        pipe, stages = m.map_pipeline(p)
        upsert(conn, "silver.pipeline", [pipe], ["hs_pipeline_id"])
        upsert(conn, "silver.stage", stages, ["hs_pipeline_id", "hs_stage_id"])
    conn.commit()


def stage_flags(conn: Conn) -> dict[tuple[str, str], tuple[bool, Decimal | None]]:
    with conn.cursor() as cur:
        cur.execute("select hs_pipeline_id, hs_stage_id, is_closed, probability from silver.stage")
        return {(r["hs_pipeline_id"], r["hs_stage_id"]): (r["is_closed"], r["probability"]) for r in cur.fetchall()}


# ---- one window of one object type ---------------------------------------------
async def sync_window(conn: Conn, client: HubSpotClient, object_type: str, start: datetime, end: datetime) -> int:
    props = hubspot_properties()
    modified = props["modified_property"][object_type]
    fields = list(dict.fromkeys(props[object_type] + [modified]))
    objs = [o async for o in client.search_window(object_type, modified, fields, start, end)]
    if not objs:
        return 0
    upsert(conn, "bronze.hubspot_raw", [
        {"object_type": object_type, "object_id": str(o["id"]), "payload": Jsonb(o),
         "hs_updated_at": m.parse_ts((o.get("properties") or {}).get(modified))} for o in objs],
        ["object_type", "object_id"])
    ids = [str(o["id"]) for o in objs]
    if object_type == "contacts":
        upsert(conn, "silver.contact", [m.map_contact(o) for o in objs], ["hs_contact_id"])
    elif object_type == "companies":
        upsert(conn, "silver.company", [m.map_company(o) for o in objs], ["hs_company_id"])
    elif object_type == "deals":
        await _sync_deals(conn, client, objs, ids)
    else:
        await _sync_activities(conn, client, object_type, objs, ids)
    return len(objs)


async def _sync_deals(conn: Conn, client: HubSpotClient, objs: list[dict[str, Any]], ids: list[str]) -> None:
    flags = stage_flags(conn)
    stage_to_pipeline = {s: p for (p, s) in flags}
    hist_props = hubspot_properties()["history_properties"]
    history = {str(d["id"]): d.get("propertiesWithHistory", {}) for d in await client.deals_with_history(ids, hist_props)}
    rows = []
    for o in objs:
        row = m.map_deal(o, flags)
        row["close_date_pushes"] = m.close_date_pushes(history.get(row["hs_deal_id"], {}).get("closedate", []))
        rows.append(row)
    upsert(conn, "silver.deal", rows, ["hs_deal_id"])
    stages, changes = [], []
    for did, h in history.items():
        stages += m.stage_history(did, h.get("dealstage", []), stage_to_pipeline)
        for prop, hs_prop in (("dealstage", "dealstage"), ("amount", "amount"), ("closedate", "closedate"),
                              ("hubspot_owner_id", "hubspot_owner_id")):
            changes += m.property_changes(did, prop, h.get(hs_prop, []))
    upsert(conn, "silver.deal_stage_history", stages, ["hs_deal_id", "hs_stage_id", "entered_at"])
    upsert(conn, "silver.deal_property_change", changes, ["hs_deal_id", "property", "changed_at"])
    for to_type, table, col in (("contacts", "silver.deal_contact", "hs_contact_id"),
                                ("companies", "silver.deal_company", "hs_company_id")):
        assoc = await client.associations("deals", to_type, ids)
        upsert(conn, table, [{"hs_deal_id": d, col: t} for d, ts in assoc.items() for t in ts], ["hs_deal_id", col])


async def _sync_activities(conn: Conn, client: HubSpotClient, object_type: str,
                           objs: list[dict[str, Any]], ids: list[str]) -> None:
    rows = [m.map_activity(object_type, o) for o in objs]
    by_id = {r["hs_activity_id"]: r for r in rows}
    kind = m.ACTIVITY_TYPES[object_type]
    for to_type, key in (("deals", "hs_deal_id"), ("contacts", "hs_contact_id")):
        for src, targets in (await client.associations(object_type, to_type, ids)).items():
            if targets and f"{kind}:{src}" in by_id:
                by_id[f"{kind}:{src}"][key] = targets[0]
    upsert(conn, "silver.activity", rows, ["hs_activity_id"])


# ---- archived flags -------------------------------------------------------------
async def sync_archived(conn: Conn, client: HubSpotClient) -> int:
    n = 0
    async for o in client.archived("deals", ["hs_lastmodifieddate"]):
        with conn.cursor() as cur:
            cur.execute("update silver.deal set is_archived = true where hs_deal_id = %s", (str(o["id"]),))
        n += 1
    conn.commit()
    return n


# ---- backfill (resumable) ---------------------------------------------------------
def plan_windows(start: datetime, end: datetime, days: int = 30) -> list[tuple[datetime, datetime]]:
    out, cur = [], start
    while cur < end:
        nxt = min(cur + timedelta(days=days), end)
        out.append((cur, nxt))
        cur = nxt
    return out


async def backfill(conn: Conn, client: HubSpotClient, since: datetime, *, now: datetime | None = None,
                   window_days: int = 30, objects: list[str] | None = None) -> dict[str, int]:
    """Windows are persisted; completed ones are skipped when the job restarts (FR-ING-3)."""
    now = now or datetime.now(UTC)
    await sync_metadata(conn, client)
    totals: dict[str, int] = {}
    for obj in objects or OBJECT_ORDER:
        for ws, we in plan_windows(since, now, window_days):
            with conn.cursor() as cur:
                cur.execute("insert into app.ingest_window (job, object_type, window_start, window_end) "
                            "values ('backfill', %s, %s, %s) on conflict do nothing", (obj, ws, we))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("select window_start, window_end from app.ingest_window where job='backfill' "
                        "and object_type=%s and status<>'done' order by window_start", (obj,))
            pending = [(r["window_start"], r["window_end"]) for r in cur.fetchall()]
        for ws, we in pending:
            try:
                n = await sync_window(conn, client, obj, ws, we)
            except Exception as exc:
                conn.rollback()
                with conn.cursor() as cur:
                    cur.execute("update app.ingest_window set status='failed', attempts=attempts+1, error=%s, "
                                "updated_at=now() where job='backfill' and object_type=%s and window_start=%s "
                                "and window_end=%s", (type(exc).__name__, obj, ws, we))
                conn.commit()
                raise
            with conn.cursor() as cur:
                cur.execute("update app.ingest_window set status='done', row_count=%s, updated_at=now() "
                            "where job='backfill' and object_type=%s and window_start=%s and window_end=%s",
                            (n, obj, ws, we))
            conn.commit()  # data + window marker commit together
            totals[obj] = totals.get(obj, 0) + n
        with conn.cursor() as cur:  # seed the incremental cursor at the backfill horizon
            cur.execute("insert into app.ingest_cursor (object_type, high_watermark) values (%s, %s) "
                        "on conflict (object_type) do update set high_watermark = greatest("
                        "app.ingest_cursor.high_watermark, excluded.high_watermark), updated_at = now()", (obj, now))
        conn.commit()
    await sync_archived(conn, client)
    return totals


# ---- incremental (every 15 min) ------------------------------------------------------
async def incremental(conn: Conn, client: HubSpotClient, *, now: datetime | None = None,
                      objects: list[str] | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    await sync_metadata(conn, client)
    totals: dict[str, int] = {}
    for obj in objects or OBJECT_ORDER:
        with conn.cursor() as cur:
            cur.execute("select high_watermark from app.ingest_cursor where object_type=%s", (obj,))
            row = cur.fetchone()
        if not row:
            raise RuntimeError(f"no cursor for {obj}: run `omnidata ingest backfill` first")
        n = await sync_window(conn, client, obj, row["high_watermark"] - INCREMENTAL_OVERLAP, now)
        with conn.cursor() as cur:
            cur.execute("update app.ingest_cursor set high_watermark=%s, updated_at=now() where object_type=%s",
                        (now, obj))
        conn.commit()
        totals[obj] = n
    return totals


# ---- snapshots (FR-ING-4) --------------------------------------------------------------
def weekly_snapshot(conn: Conn, on: date | None = None) -> int:
    on = on or datetime.now(UTC).date()
    with conn.cursor() as cur:
        cur.execute(
            "insert into silver.deal_snapshot (snapshot_date, hs_deal_id, hs_stage_id, amount, close_date, "
            "hs_owner_id, is_open) select %s, hs_deal_id, hs_stage_id, amount, close_date, hs_owner_id, is_open "
            "from silver.deal where not is_archived on conflict (snapshot_date, hs_deal_id) do update set "
            "hs_stage_id=excluded.hs_stage_id, amount=excluded.amount, close_date=excluded.close_date, "
            "hs_owner_id=excluded.hs_owner_id, is_open=excluded.is_open", (on,))
        n = cur.rowcount
    conn.commit()
    return n
