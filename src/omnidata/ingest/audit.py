"""Data-readiness audit (FR-ING-5): baselines for G2-G4 and go/no-go per use case (§15, M0 exit)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import psycopg

from ..config import get_settings, hubspot_properties
from ..crm.hubspot.client import HubSpotClient

Conn = psycopg.Connection[Any]
NON_REASONS = ("", "other", "outro", "outros")


# ---- properties audit ---------------------------------------------------------------
async def audit_properties(client: HubSpotClient) -> dict[str, Any]:
    """Compare the expected property names in config with the real schema. Never guess names."""
    expected = hubspot_properties()
    report: dict[str, Any] = {}
    for obj in ("deals", "contacts", "companies", "calls", "meetings", "emails", "notes", "tasks"):
        schema = {p["name"]: p.get("type") for p in await client.property_schema(obj)}
        report[obj] = {
            "found": {n: schema[n] for n in expected[obj] if n in schema},
            "missing": [n for n in expected[obj] if n not in schema],
        }
    return report


def render_properties_md(report: dict[str, Any]) -> str:
    lines = ["# HubSpot property audit", ""]
    for obj, r in report.items():
        lines += [f"## {obj}", f"- found: {len(r['found'])} · missing: {len(r['missing'])}"]
        lines += [f"  - `{n}` ({t})" for n, t in r["found"].items()]
        lines += [f"  - **MISSING** `{n}` — fix `config/hubspot_properties.yaml`" for n in r["missing"]]
        lines.append("")
    return "\n".join(lines)


# ---- readiness audit ----------------------------------------------------------------
@dataclass
class UseCase:
    name: str
    decision: str  # go | no-go | conditional
    reason: str


@dataclass
class Readiness:
    generated_at: str
    closed_per_pipeline: dict[str, dict[str, int]]
    pct_intact_stage_history: float | None
    pct_lost_with_reason: float | None
    lost_deals: int
    avg_contacts_per_deal: float | None
    pct_calls_with_transcript: float | None
    calls_with_transcript: int
    quota_rows: int
    owners_active: int
    owners_mapped_to_phone: int
    use_cases: list[UseCase] = field(default_factory=list)


def decide(r: Readiness, model_min_closed: int = 300) -> list[UseCase]:
    ucs = []
    per_pipe = {p: v["won"] + v["lost"] for p, v in r.closed_per_pipeline.items()}
    ok_pipes = [p for p, n in per_pipe.items() if n >= model_min_closed]
    ucs.append(UseCase("Predictive scoring", "go" if ok_pipes else "no-go",
                       f"pipelines with >= {model_min_closed} closed deals (24 mo): {ok_pipes or 'none'}"))
    if r.lost_deals == 0:
        ucs.append(UseCase("Win/loss analysis", "no-go", "no closed-lost deals in the last 24 months"))
    elif (r.pct_lost_with_reason or 0) >= 0.8:
        ucs.append(UseCase("Win/loss analysis", "go", f"{r.pct_lost_with_reason:.0%} of losses have a reason"))
    else:
        ucs.append(UseCase("Win/loss analysis", "conditional",
                           f"only {(r.pct_lost_with_reason or 0):.0%} of losses have a structured reason (G2 target 80%); "
                           "ship loss-reason capture (FR-WL-1) first"))
    ucs.append(UseCase("Script adherence", "go" if r.calls_with_transcript >= 50 else "no-go",
                       f"{r.calls_with_transcript} calls with transcript (need >= 50 for validation, OPEN-4)"))
    ucs.append(UseCase("Quota forecast", "go" if r.quota_rows > 0 else "no-go",
                       f"{r.quota_rows} quota rows (OPEN-2)"))
    return ucs


def _one(conn: Conn, q: str) -> Any:
    with conn.cursor() as cur:
        cur.execute(q)
        row = cur.fetchone()
    return next(iter(row.values())) if row else None


def readiness(conn: Conn) -> Readiness:
    with conn.cursor() as cur:
        cur.execute("""select hs_pipeline_id, count(*) filter (where is_won) as won,
                       count(*) filter (where is_lost) as lost from silver.deal
                       where not is_open and not is_archived and closed_at >= now() - interval '24 months'
                       group by 1 order by 1""")
        per = {r["hs_pipeline_id"]: {"won": r["won"], "lost": r["lost"]} for r in cur.fetchall()}
    closed = _one(conn, "select count(*) from silver.deal where not is_open and not is_archived")
    intact = _one(conn, """select count(*) from silver.deal d where not d.is_open and not d.is_archived
                           and exists (select 1 from silver.deal_stage_history h where h.hs_deal_id = d.hs_deal_id)""")
    lost = _one(conn, "select count(*) from silver.deal where is_lost and not is_archived "
                      "and closed_at >= now() - interval '24 months'")
    with_reason = _one(conn, "select count(*) from silver.deal where is_lost and not is_archived "
                             "and closed_at >= now() - interval '24 months' and lower(trim(coalesce(lost_reason_hs,''))) "
                             f"not in {NON_REASONS!r}")
    calls = _one(conn, "select count(*) from silver.activity where activity_type='call'")
    calls_t = _one(conn, "select count(*) from silver.activity where activity_type='call' and transcript_path is not null")
    r = Readiness(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        closed_per_pipeline=per,
        pct_intact_stage_history=(intact / closed) if closed else None,
        pct_lost_with_reason=(with_reason / lost) if lost else None,
        lost_deals=lost,
        avg_contacts_per_deal=_one(conn, "select round(avg(num_contacts)::numeric, 2) from silver.deal where not is_archived"),
        pct_calls_with_transcript=(calls_t / calls) if calls else None,
        calls_with_transcript=calls_t,
        quota_rows=_one(conn, "select count(*) from silver.quota"),
        owners_active=_one(conn, "select count(*) from silver.owner where is_active"),
        owners_mapped_to_phone=_one(conn, "select count(*) from app.app_user"),
    )
    r.use_cases = decide(r, get_settings().model_min_closed)
    return r


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def render_readiness_md(r: Readiness) -> str:
    lines = [f"# OmniData data-readiness audit — {r.generated_at}", "", "## Baselines", "",
             f"- Intact stage history (closed deals): {_pct(r.pct_intact_stage_history)}",
             f"- Closed-lost with structured reason (G2 baseline): {_pct(r.pct_lost_with_reason)} of {r.lost_deals}",
             f"- Avg contacts per deal: {r.avg_contacts_per_deal}",
             f"- Calls with recording/transcript: {_pct(r.pct_calls_with_transcript)} ({r.calls_with_transcript})",
             f"- Quota rows: {r.quota_rows}",
             f"- Owners active: {r.owners_active} · mapped to a phone: {r.owners_mapped_to_phone}", "",
             "## Closed deals per pipeline (24 months)", "", "| pipeline | won | lost |", "|---|---|---|"]
    lines += [f"| {p} | {v['won']} | {v['lost']} |" for p, v in r.closed_per_pipeline.items()]
    lines += ["", "## Go / no-go per use case", "", "| use case | decision | why |", "|---|---|---|"]
    lines += [f"| {u.name} | **{u.decision}** | {u.reason} |" for u in r.use_cases]
    return "\n".join(lines) + "\n"


def readiness_json(r: Readiness) -> str:
    return json.dumps(asdict(r), indent=2, default=str)
