"""Alert engine (FR-ALR-1..3): rules on serving.v_deal_health, stable dedupe keys, budget, quiet hours, snooze, telemetry."""
from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from ..bot import strings_ptbr as S
from ..bot.gateway import MessagingGateway
from ..config import Settings

Conn = psycopg.Connection[Any]

# rule_key -> (health flag, dedupe_key template)
RULES: dict[str, tuple[str, str]] = {
    "stalled_stage": ("stalled", "stalled:{deal}:{stage}"),
    "close_date_overdue": ("close_date_overdue", "overdue:{deal}"),
    "no_next_step": ("no_next_step", "nostep:{deal}:{week}"),
    "gone_quiet": ("gone_quiet", "quiet:{deal}:{week}"),
    "amount_swing": ("amount_swing", "swing:{deal}:{date}"),
}
REASON = {"stalled_stage": "está parado na etapa há mais tempo que o normal", "close_date_overdue": "a data de fechamento venceu",
          "no_next_step": "está sem próximo passo", "gone_quiet": "está sem atividade há vários dias",
          "amount_swing": "o valor mudou mais de 20%"}


def evaluate(conn: Conn, now: datetime | None = None) -> int:
    """Create alert_event rows for every visible firing (unique per user+dedupe_key, so re-runs are idempotent)."""
    now = now or datetime.now(UTC)
    iso = now.isocalendar()
    week, date_s = f"{iso.year}-W{iso.week:02d}", now.date().isoformat()
    created = 0
    with conn.cursor() as cur:
        cur.execute("select id, hs_owner_id, role from app.app_user where status='active'")
        users = cur.fetchall()
        for u in users:
            scope, params = "hs_owner_id = %s", [u["hs_owner_id"]]  # alerts are push about the user's OWN deals; team views are pull
            cur.execute(f"select hs_deal_id, hs_stage_id, health_flags, attention_score from serving.v_deal_health where {scope} "
                        "and cardinality(health_flags) > 0", params)
            for d in cur.fetchall():
                for rule, (flag, tpl) in RULES.items():
                    if flag not in d["health_flags"]:
                        continue
                    key = tpl.format(deal=d["hs_deal_id"], stage=d["hs_stage_id"], week=week, date=date_s)
                    cur.execute("select 1 from app.alert_event where user_id=%s and hs_deal_id=%s and rule_key=%s "
                                "and created_at > now() - interval '3 days'", (u["id"], d["hs_deal_id"], rule))
                    if cur.fetchone():
                        continue  # one alert per deal per rule per 3 days
                    cur.execute("insert into app.alert_event (user_id, rule_key, dedupe_key, hs_deal_id, attention_score) "
                                "values (%s,%s,%s,%s,%s) on conflict (user_id, dedupe_key) do nothing",
                                (u["id"], rule, key, d["hs_deal_id"], d["attention_score"]))
                    created += cur.rowcount
    conn.commit()
    return created


def _in_quiet_hours(now_local: datetime, start: str, end: str) -> bool:
    s, e = time.fromisoformat(start), time.fromisoformat(end)
    t = now_local.time()
    return (t >= s or t < e) if s > e else (s <= t < e)


async def dispatch(conn: Conn, gw: MessagingGateway, settings: Settings, now: datetime | None = None) -> int:
    """Send pending events: highest attention first, capped per user per day, never in quiet hours, respecting snooze."""
    now = now or datetime.now(UTC)
    sent = 0
    with conn.cursor() as cur:
        cur.execute("select id, phone_e164, timezone from app.app_user where status='active'")
        users = cur.fetchall()
    for u in users:
        local = now.astimezone(ZoneInfo(u["timezone"]))
        if _in_quiet_hours(local, settings.alert_quiet_start, settings.alert_quiet_end):
            continue
        with conn.cursor() as cur:
            cur.execute("select count(*) n from app.alert_event where user_id=%s and sent_at >= date_trunc('day', %s::timestamptz at time zone %s) at time zone %s",
                        (u["id"], now, u["timezone"], u["timezone"]))
            already = int(cur.fetchone()["n"])
            room = settings.alert_daily_cap - already
            if room <= 0:
                continue
            cur.execute("select e.id, e.rule_key, e.hs_deal_id, d.name from app.alert_event e join serving.v_deal_health d using (hs_deal_id) "
                        "where e.user_id=%s and e.sent_at is null and (e.snoozed_until is null or e.snoozed_until < now()) "
                        "and not exists (select 1 from app.alert_event s where s.user_id=e.user_id and s.hs_deal_id=e.hs_deal_id and s.snoozed_until > now()) "
                        "order by e.attention_score desc limit %s", (u["id"], room))
            batch = cur.fetchall()
        for e in batch:
            await gw.send_template(u["phone_e164"], "alert_deal_v1", [e["name"], REASON[e["rule_key"]]], quick_reply_payload=f"act:open:{e['id']}")
            with conn.cursor() as cur:
                cur.execute("update app.alert_event set sent_at=now() where id=%s", (e["id"],))
            conn.commit()
            sent += 1
    return sent


async def morning_briefs(conn: Conn, gw: MessagingGateway, now: datetime | None = None) -> int:
    """FR-BOT-4: template at each user's brief_time on business days; the 'Ver meu dia' tap opens the 24h window."""
    now = now or datetime.now(UTC)
    n = 0
    with conn.cursor() as cur:
        cur.execute("select id, phone_e164, display_name, timezone, brief_time from app.app_user where status='active'")
        users = cur.fetchall()
    for u in users:
        local = now.astimezone(ZoneInfo(u["timezone"]))
        if local.weekday() >= 5 or local.time() < u["brief_time"]:
            continue
        with conn.cursor() as cur:
            cur.execute("select 1 from app.audit_log where user_id=%s and event='morning_brief_sent' and (detail->>'date') = %s",
                        (u["id"], local.date().isoformat()))
            if cur.fetchone():
                continue
            cur.execute("select count(*) n from serving.v_deal_health where hs_owner_id = (select hs_owner_id from app.app_user where id=%s) "
                        "and cardinality(health_flags) > 0", (u["id"],))
            k = int(cur.fetchone()["n"])
        await gw.send_template(u["phone_e164"], "morning_brief_v1", [u["display_name"] or "", str(min(k, 5))], quick_reply_payload="act:open:brief")
        with conn.cursor() as cur:
            cur.execute("insert into app.audit_log (user_id, event, detail) values (%s,'morning_brief_sent', jsonb_build_object('date', %s::text))",
                        (u["id"], local.date().isoformat()))
        conn.commit()
        n += 1
    return n


async def evening_recaps(conn: Conn, gw: MessagingGateway, now: datetime | None = None) -> int:
    """Push at (or after) 18:00 local time: what got done today + where to start tomorrow. Same gate/dedupe shape as
    morning_briefs, but sends the text straight away — send_template is a Meta Cloud API leftover Evolution just
    flattens to plain text anyway (bot/evolution.py), so there is no reason to make the seller tap a button first."""
    now = now or datetime.now(UTC)
    n = 0
    with conn.cursor() as cur:
        cur.execute("select id, hs_owner_id, phone_e164, display_name, timezone from app.app_user where status='active'")
        users = cur.fetchall()
    for u in users:
        local = now.astimezone(ZoneInfo(u["timezone"]))
        if local.weekday() >= 5 or local.time() < time(18, 0):
            continue
        with conn.cursor() as cur:
            cur.execute("select 1 from app.audit_log where user_id=%s and event='evening_recap_sent' and (detail->>'date') = %s",
                        (u["id"], local.date().isoformat()))
            if cur.fetchone():
                continue
        day = local.date()
        with conn.cursor() as cur:
            cur.execute("select count(*) n, coalesce(sum(amount),0) amt from silver.deal "
                        "where hs_owner_id=%s and is_won and closed_at::date = %s", (u["hs_owner_id"], day))
            won = cur.fetchone()
            cur.execute("select count(*) n from serving.v_activity where hs_owner_id=%s and activity_type='note' and occurred_at::date = %s",
                        (u["hs_owner_id"], day))
            notes = cur.fetchone()
            cur.execute("select name from serving.v_deal_health where hs_owner_id=%s and cardinality(health_flags) > 0 "
                        "order by attention_score desc limit 3", (u["hs_owner_id"],))
            tomorrow = [{"name": r["name"]} for r in cur.fetchall()]
        text = S.tpl_evening_recap({"name": u["display_name"], "won_count": int(won["n"]), "won_amount": float(won["amt"]),
                                    "notes_count": int(notes["n"]), "tomorrow": tomorrow})
        await gw.send_text(u["phone_e164"], text)
        with conn.cursor() as cur:
            cur.execute("insert into app.audit_log (user_id, event, detail) values (%s,'evening_recap_sent', jsonb_build_object('date', %s::text))",
                        (u["id"], local.date().isoformat()))
        conn.commit()
        n += 1
    return n
