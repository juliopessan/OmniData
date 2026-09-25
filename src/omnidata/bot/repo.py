"""Read repositories: serving.* only, ALWAYS scoped by Principal (FR-BOT-2). No function takes an owner id from callers."""
from __future__ import annotations

import re
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


def team_status(conn: Conn, p: Principal, period_start: date) -> dict[str, Any]:
    """For managers: attainment + open hygiene issues per rep this Principal can see, worst attainment first, to help
    prioritize 1:1s. For a rep, owner_clause() naturally narrows this to just themselves — same scoping, no special case."""
    k_clause, k_params = p.owner_clause("k.hs_owner_id")
    with conn.cursor() as cur:
        cur.execute(f"select k.hs_owner_id, o.first_name, o.last_name, sum(k.quota_amount) q, coalesce(sum(k.won_amount),0) w, sum(k.gap) g "
                    f"from serving.v_rep_kpis k left join silver.owner o using (hs_owner_id) "
                    f"where k.period_start = %s and {k_clause} "
                    f"group by k.hs_owner_id, o.first_name, o.last_name", [period_start, *k_params])
        kpi_rows = cur.fetchall()
        clause, params = p.owner_clause()
        cur.execute(f"select hs_owner_id, count(*) filter (where next_activity_at is null) n from serving.v_hygiene_facts "
                    f"where {clause} group by hs_owner_id", params)
        issues = {r["hs_owner_id"]: r["n"] for r in cur.fetchall()}
    reps = []
    for r in kpi_rows:
        quota = float(r["q"]) if r["q"] is not None else None
        won = float(r["w"])
        name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or r["hs_owner_id"]
        reps.append({"hs_owner_id": r["hs_owner_id"], "name": name, "quota_amount": quota, "won_amount": won,
                     "gap": float(r["g"]) if r["g"] is not None else None, "attainment": (won / quota) if quota else None,
                     "open_issues": issues.get(r["hs_owner_id"], 0)})
    reps.sort(key=lambda x: x["attainment"] if x["attainment"] is not None else -1)
    return {"period": period_start.isoformat(), "reps": reps}


def goal_status(conn: Conn, p: Principal, today: date) -> dict[str, Any]:
    """Progress on the seller's own active personal goal (Aurora). Scoped to this Principal's own row, not owner_clause()
    — a personal goal is never a team view, even for a manager."""
    with conn.cursor() as cur:
        cur.execute("select goal_type, target, deadline, created_at from serving.v_seller_goal "
                    "where user_id=%s and status='active' order by created_at desc limit 1", (p.user_id,))
        g = cur.fetchone()
    if not g:
        return {"active": False}
    target = float(g["target"])
    if g["goal_type"] == "deals_won":
        with conn.cursor() as cur:
            cur.execute("select count(*) n from silver.deal where hs_owner_id=%s and is_won and closed_at >= %s",
                        (p.hs_owner_id, g["created_at"]))
            progress = float(cur.fetchone()["n"])
    else:
        q = quota_status(conn, p, month_start(today))
        progress = round((q["attainment"] or 0) * 100, 1)
    return {"active": True, "goal_type": g["goal_type"], "target": target, "progress": progress,
            "deadline": g["deadline"].isoformat(), "done": progress >= target}


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
                       "flags": list(r["health_flags"])} for r in rows]}  # attention_score decides the order only, never shown or narrated


_AMOUNT = re.compile(r"\([^)]*\)|R\$\s*[\d.,]+", re.IGNORECASE)


def deal_query_tokens(query: str) -> list[str]:
    """What a seller pastes back is often the bot's own list line: "Empresa 890 – Novo (R$ 120.000)". The amount and any
    parenthetical are not part of the name, and a token that fails to match drops every result (all tokens must match)."""
    words = (w.strip("()[]{}.,;:!?\"'“”") for w in _AMOUNT.sub(" ", query).replace("–", " ").replace("—", " ").replace("-", " ").split())
    return [w for w in words if len(w) > 1][:5]


def normalize_deal_name(name: str) -> str:
    return " ".join(deal_query_tokens(name)).lower()


def find_deals(conn: Conn, p: Principal, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fuzzy by name (all tokens must match) among deals THIS principal can see — by name or by id. A number matches as a
    whole word, so "Empresa 890" never also returns "Empresa 1890"."""
    clause, params = p.owner_clause()
    tokens = deal_query_tokens(query)
    if not tokens:
        return []
    conds: list[str] = []
    args: list[Any] = []
    for t in tokens:
        if t.isdigit():
            conds.append("(name ~* %s or hs_deal_id = %s)")
            args += [rf"\m{t}\M", t]
        else:
            conds.append("(name ilike %s or hs_deal_id = %s)")
            args += [f"%{t}%", t]
    like = " and ".join(conds)
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


def meeting_transcripts_by_ids(conn: Conn, p: Principal, ids: list[str]) -> list[dict[str, Any]]:
    """The permission boundary for Atlas (ADR 0009): Chroma only ever suggests candidate ids; this is what decides which of
    them this Principal may actually see. Never trust a caller-supplied owner id (rule 7) — owner_clause() decides that."""
    if not ids:
        return []
    clause, params = p.owner_clause()
    with conn.cursor() as cur:
        cur.execute(f"select id, hs_deal_id, deal_name, occurred_at, text from serving.v_meeting_transcript "
                    f"where id = any(%s::uuid[]) and {clause}", [ids, *params])
        return list(cur.fetchall())
