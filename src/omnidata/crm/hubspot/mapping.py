"""Pure functions: HubSpot payloads -> silver rows. No I/O, fully unit-testable."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

Row = dict[str, Any]
ACTIVITY_TYPES = {"calls": "call", "meetings": "meeting", "emails": "email", "notes": "note", "tasks": "task"}


def parse_ts(v: Any) -> datetime | None:
    """HubSpot returns ISO-8601 strings or epoch milliseconds (as str/int)."""
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    s = str(v)
    if s.lstrip("-").isdigit():
        return datetime.fromtimestamp(int(s) / 1000, tz=UTC)
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_amount(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v)) if v not in (None, "") else None
    except InvalidOperation:
        return None


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _bool(v: Any) -> bool:
    return str(v).lower() == "true"


def map_owner(o: Row) -> Row:
    return {"hs_owner_id": str(o["id"]), "email": o.get("email"), "first_name": o.get("firstName"),
            "last_name": o.get("lastName"), "is_active": not o.get("archived", False)}


def map_pipeline(p: Row) -> tuple[Row, list[Row]]:
    pipe = {"hs_pipeline_id": str(p["id"]), "label": p["label"]}
    stages = []
    for s in p.get("stages", []):
        meta = s.get("metadata") or {}
        prob = meta.get("probability")
        stages.append({
            "hs_pipeline_id": str(p["id"]), "hs_stage_id": str(s["id"]), "label": s["label"],
            "display_order": _int(s.get("displayOrder")), "is_closed": _bool(meta.get("isClosed")),
            "probability": Decimal(str(prob)) if prob not in (None, "") else None,
        })
    return pipe, stages


def map_deal(o: Row, stage_flags: dict[tuple[str, str], tuple[bool, Decimal | None]]) -> Row:
    """Won/lost derive from stage metadata (is_closed + probability 1.0/0.0), never from names (§10.1)."""
    p = o.get("properties", {})
    pipeline, stage = str(p.get("pipeline") or ""), str(p.get("dealstage") or "")
    is_closed, prob = stage_flags.get((pipeline, stage), (False, None))
    is_won = is_closed and prob == Decimal("1")
    is_lost = is_closed and prob == Decimal("0")
    close_date = parse_ts(p.get("closedate"))
    return {
        "hs_deal_id": str(o["id"]), "name": p.get("dealname"), "amount": parse_amount(p.get("amount")),
        "currency": p.get("deal_currency_code"), "hs_pipeline_id": pipeline, "hs_stage_id": stage,
        "hs_owner_id": p.get("hubspot_owner_id") or None, "created_at": parse_ts(p.get("createdate")),
        "close_date": close_date, "closed_at": close_date if is_closed else None,
        "is_open": not is_closed, "is_won": is_won, "is_lost": is_lost,
        "lost_reason_hs": (p.get("closed_lost_reason") or None) if is_lost else None,
        "source": p.get("hs_analytics_source"),
        "last_activity_at": parse_ts(p.get("notes_last_contacted")),
        "next_activity_at": parse_ts(p.get("notes_next_activity_date")),
        "num_contacts": _int(p.get("num_associated_contacts")),
        "hs_updated_at": parse_ts(p.get("hs_lastmodifieddate")) or datetime.now(UTC),
        "is_archived": bool(o.get("archived", False)),
    }


def map_contact(o: Row) -> Row:
    p = o.get("properties", {})
    email = (p.get("email") or "").strip().lower()
    return {"hs_contact_id": str(o["id"]),
            "email_hash": hashlib.sha256(email.encode()).hexdigest() if email else None,  # no raw PII in silver
            "job_title": p.get("jobtitle"), "lifecycle_stage": p.get("lifecyclestage"),
            "hs_owner_id": p.get("hubspot_owner_id") or None,
            "hs_updated_at": parse_ts(p.get("lastmodifieddate") or p.get("hs_lastmodifieddate"))}


def employee_band(n: Any) -> str | None:
    if n in (None, ""):
        return None
    v = _int(n, -1)
    if v < 0:
        return None
    for limit, label in ((10, "1-10"), (50, "11-50"), (200, "51-200"), (1000, "201-1000")):
        if v <= limit:
            return label
    return "1000+"


def map_company(o: Row) -> Row:
    p = o.get("properties", {})
    return {"hs_company_id": str(o["id"]), "name": p.get("name"), "industry": p.get("industry"),
            "employee_band": employee_band(p.get("numberofemployees")),
            "hs_updated_at": parse_ts(p.get("hs_lastmodifieddate"))}


def map_activity(object_type: str, o: Row) -> Row:
    """Emails are metadata only (no body). Ids are namespaced by type to avoid collisions."""
    kind = ACTIVITY_TYPES[object_type]
    p = o.get("properties", {})
    row: Row = {
        "hs_activity_id": f"{kind}:{o['id']}", "activity_type": kind, "hs_deal_id": None, "hs_contact_id": None,
        "hs_owner_id": p.get("hubspot_owner_id") or None, "occurred_at": parse_ts(p.get("hs_timestamp")),
        "due_at": None, "is_completed": None, "duration_sec": None, "direction": None, "outcome": None,
        "summary": None, "transcript_path": None, "hs_updated_at": parse_ts(p.get("hs_lastmodifieddate")),
    }
    if kind == "call":
        row.update(duration_sec=_int(p.get("hs_call_duration")) // 1000 if p.get("hs_call_duration") else None,
                   direction=p.get("hs_call_direction"), outcome=p.get("hs_call_disposition"),
                   summary=(p.get("hs_call_body") or None) and p["hs_call_body"][:500],
                   transcript_path=p.get("hs_call_transcription_id") or p.get("hs_call_recording_url") or None)
    elif kind == "meeting":
        row.update(occurred_at=parse_ts(p.get("hs_meeting_start_time")) or row["occurred_at"],
                   outcome=p.get("hs_meeting_outcome"),
                   summary=(p.get("hs_meeting_body") or None) and p["hs_meeting_body"][:500])
    elif kind == "email":
        row.update(direction=p.get("hs_email_direction"))
    elif kind == "note":
        row.update(summary=(p.get("hs_note_body") or None) and p["hs_note_body"][:500])
    elif kind == "task":
        status = p.get("hs_task_status")
        row.update(due_at=parse_ts(p.get("hs_timestamp")), is_completed=(status == "COMPLETED"),
                   outcome=status, summary=p.get("hs_task_subject"))
    return row


# ---- property history (FR-ING-2) --------------------------------------------
def _versions(history: list[Row]) -> list[tuple[datetime, str | None]]:
    out = [(parse_ts(v["timestamp"]), v.get("value")) for v in history if v.get("timestamp")]
    return sorted(((t, val) for t, val in out if t is not None), key=lambda x: x[0])


def stage_history(deal_id: str, history: list[Row], stage_to_pipeline: dict[str, str]) -> list[Row]:
    vs = _versions(history)
    rows = []
    for i, (ts, stage) in enumerate(vs):
        if not stage:
            continue
        rows.append({"hs_deal_id": deal_id, "hs_pipeline_id": stage_to_pipeline.get(stage, ""),
                     "hs_stage_id": stage, "entered_at": ts,
                     "exited_at": vs[i + 1][0] if i + 1 < len(vs) else None})
    return rows


def property_changes(deal_id: str, prop: str, history: list[Row]) -> list[Row]:
    vs = _versions(history)
    return [{"hs_deal_id": deal_id, "property": prop, "old_value": vs[i - 1][1] if i else None,
             "new_value": val, "changed_at": ts} for i, (ts, val) in enumerate(vs)]


def close_date_pushes(history: list[Row]) -> int:
    """Number of changes where the new close date is later than the old one."""
    vs = _versions(history)
    n = 0
    for (_, old), (_, new) in zip(vs, vs[1:], strict=False):
        o, w = parse_ts(old), parse_ts(new)
        if o and w and w > o:
            n += 1
    return n
