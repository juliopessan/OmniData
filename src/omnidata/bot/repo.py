"""Read repositories: serving.* only, ALWAYS scoped by Principal (FR-BOT-2). No function takes an owner id from callers."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from ..config import get_settings
from ..metrics import wilson
from ..security.principal import Principal

Conn = psycopg.Connection[Any]


def month_start(today: date, which: str = "this_month") -> date:
    first = today.replace(day=1)
    if which == "last_month":
        return (first - timedelta(days=1)).replace(day=1)
    return first


def kpis(conn: Conn, p: Principal, period_start: date) -> dict[str, Any]:
    clause, params = p.owner_clause()
    with conn.cursor() as cur:
        cur.execute(f"select coalesce(sum(won_count),0) w, coalesce(sum(lost_count),0) l, coalesce(sum(won_amount),0) amt, "
                    f"count(*) filter (where won_count > 0) reps, min(median_cycle_days) cyc, max(avg_deal_size) avg_size "
                    f"from serving.v_rep_kpis where period_start = %s and {clause}", [period_start, *params])
        r = cur.fetchone()
    n = int(r["w"]) + int(r["l"])
    lo, hi = wilson(int(r["w"]), n)
    return {"period": period_start.isoformat(), "n_closed": n, "won_count": int(r["w"]), "lost_count": int(r["l"]),
            "won_amount": float(r["amt"]), "win_rate": (int(r["w"]) / n) if n else None,
            "ci_low": lo if n else None, "ci_high": hi if n else None, "low_n": n < 20,
            "median_cycle_days": float(r["cyc"]) if r["cyc"] is not None else None,
            "avg_deal_size": float(r["avg_size"]) if r["avg_size"] is not None else None}


def quota_status(conn: Conn, p: Principal, period_start: date) -> dict[str, Any]:
    clause, params = p.owner_clause()
    with conn.cursor() as cur:
        cur.execute(f"select sum(quota_amount) q, coalesce(sum(won_amount),0) w, sum(gap) g, "
                    f"coalesce(sum(open_amount_in_period),0) o, sum(won_count) wc, sum(lost_count) lc "
                    f"from serving.v_rep_kpis where period_start = %s and {clause}", [period_start, *params])
        r = cur.fetchone()
    quota = float(r["q"]) if r["q"] is not None else None
    won, gap, open_amt = float(r["w"]), float(r["g"]) if r["g"] is not None else None, float(r["o"])
    n = int(r["wc"] or 0) + int(r["lc"] or 0)
    wr = (int(r["wc"] or 0) / n) if n else None
    return {"period": period_start.isoformat(), "quota_amount": quota, "won_amount": won, "gap": gap,
            "attainment": (won / quota) if quota else None, "open_amount": open_amt,
            "coverage": round(open_amt / gap, 1) if gap else None,
            "required_coverage": round(1 / wr, 1) if wr else None}


def pipeline_summary(conn: Conn, p: Principal) -> dict[str, Any]:
    clause, params = p.owner_clause()
    with conn.cursor() as cur:
        cur.execute(f"select stage_label, min(stage_order) ord, count(*) n, coalesce(sum(amount),0) amt, "
                    f"count(*) filter (where is_stalled) st from serving.v_deal_health where {clause} "
                    f"group by stage_label order by ord", params)
        rows = cur.fetchall()
    return {"stages": [{"stage": r["stage_label"], "count": r["n"], "amount": float(r["amt"]), "stalled": r["st"]} for r in rows]}


def deals_needing_action(conn: Conn, p: Principal, limit: int = 5) -> dict[str, Any]:
    clause, params = p.owner_clause()
    with conn.cursor() as cur:
        cur.execute(f"select hs_deal_id, name, amount, health_flags, attention_score from serving.v_deal_health "
                    f"where {clause} and cardinality(health_flags) > 0 order by attention_score desc limit %s",
                    [*params, max(1, min(limit, 10))])
        rows = cur.fetchall()
    return {"deals": [{"id": r["hs_deal_id"], "name": r["name"], "amount": float(r["amount"] or 0),
                       "flags": list(r["health_flags"]), "attention_score": float(r["attention_score"])} for r in rows]}


def find_deals(conn: Conn, p: Principal, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fuzzy by name (all tokens must match) among deals THIS principal can see — by name or by id."""
    clause, params = p.owner_clause()
    tokens = [t for t in query.replace("–", " ").replace("-", " ").split() if len(t) > 1][:5]
    if not tokens:
        return []
    like = " and ".join("(name ilike %s or hs_deal_id = %s)" for _ in tokens)
    args: list[Any] = []
    for t in tokens:
        args += [f"%{t}%", t]
    with conn.cursor() as cur:
        cur.execute(f"select hs_deal_id, name, amount, stage_label, days_in_stage, health_flags, hs_pipeline_id, hs_stage_id, hs_owner_id "
                    f"from serving.v_deal_health where {clause} and {like} order by attention_score desc limit %s",
                    [*params, *args, limit])
        return [dict(r) for r in cur.fetchall()]


def get_deal_scoped(conn: Conn, p: Principal, deal_id: str) -> dict[str, Any] | None:
    clause, params = p.owner_clause()
    with conn.cursor() as cur:
        cur.execute(f"select hs_deal_id, name, amount, stage_label, days_in_stage, health_flags, hs_pipeline_id, "
                    f"hs_stage_id, hs_owner_id, close_date from serving.v_deal_health where {clause} and hs_deal_id = %s",
                    [*params, deal_id])
        r = cur.fetchone()
    return dict(r) if r else None


def data_quality(conn: Conn, p: Principal) -> dict[str, Any]:
    clause, params = p.owner_clause()
    with conn.cursor() as cur:
        cur.execute(f"select coalesce(sum(open_deals),0) o, coalesce(sum(open_with_next_step),0) n, coalesce(sum(lost_deals),0) l, "
                    f"coalesce(sum(lost_with_reason),0) r from serving.v_data_quality where {clause}", params)
        r = cur.fetchone()
    o, n, lost, rs = (int(r[k]) for k in ("o", "n", "l", "r"))
    return {"open_deals": o, "pct_next_step": (n / o) if o else None, "lost_deals": lost,
            "pct_lost_with_reason": (rs / lost) if lost else None, "reason_target": 0.8}


def insight_analysis(conn: Conn, p: Principal, limit: int = 10) -> dict[str, Any]:
    """Company insights over the deals (and their notes) this principal can see. Read-only, serving.* only."""
    from ..insights.compute import Rec, analyze
    clause, params = p.owner_clause()
    with conn.cursor() as cur:
        cur.execute(f"select hs_deal_id, name, amount, is_won, is_lost, campaign, lost_reason from serving.v_deal_facts where {clause} limit 50000", params)
        deals = cur.fetchall()
        cur.execute(f"select hs_deal_id, note from serving.v_deal_notes where {clause}", params)
        notes = cur.fetchall()
    by: dict[str, list[str]] = {}
    for n in notes:
        by.setdefault(n["hs_deal_id"], []).append(n["note"])
    recs = [Rec(d["hs_deal_id"], d["name"] or "", "won" if d["is_won"] else "lost" if d["is_lost"] else "open", d["amount"], d["campaign"],
                d["lost_reason"], by.get(d["hs_deal_id"], [])) for d in deals]
    return analyze(recs, limit)


def fix_queue(conn: Conn, p: Principal, limit: int = 8, today: date | None = None) -> dict[str, Any]:
    """Open deals with data gaps for this principal (Coach). Read-only, serving.* only; managers/admins also see owner-level items."""
    from ..hygiene.compute import Deal
    from ..hygiene.compute import fix_queue as build
    clause, params = p.owner_clause()
    with conn.cursor() as cur:
        cur.execute("select hs_deal_id, name, amount, hs_owner_id, owner_active, close_date, next_activity_at, note_count "
                    f"from serving.v_hygiene_facts where {clause} limit 50000", params)
        rows = cur.fetchall()
    deals = [Deal(r["hs_deal_id"], r["name"] or "", r["amount"], r["hs_owner_id"], r["owner_active"], r["close_date"], r["next_activity_at"], int(r["note_count"] or 0))
             for r in rows]
    return build(deals, today or datetime.now(ZoneInfo(get_settings().app_timezone)).date(), is_manager=p.role != "rep", limit=limit)


def forecast(conn: Conn, p: Principal, period_start: date) -> dict[str, Any]:
    """What the open pipeline can still add and the chance of reaching the quota. Read-only, serving.* only, scoped by Principal.
    win/loss counts and open amounts come from the deals this person may see; realized and quota from the period's KPIs."""
    from ..forecast.compute import forecast as build
    clause, params = p.owner_clause()
    q = quota_status(conn, p, period_start)
    with conn.cursor() as cur:
        cur.execute(f"select amount, is_open, is_won, is_lost, created_at from serving.v_deal_facts where {clause} limit 100000", params)
        rows = cur.fetchall()
    has_created = any(r["created_at"] is not None for r in rows)
    wins = sum(1 for r in rows if r["is_won"])
    losses = sum(1 for r in rows if r["is_lost"])
    out = build([float(r["amount"] or 0) for r in rows if r["is_open"]], wins, losses, q["won_amount"], q["quota_amount"], has_created_at=has_created)
    out["period"] = q["period"]
    return out
