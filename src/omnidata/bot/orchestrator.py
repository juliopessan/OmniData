"""Deterministic orchestrator (D7, §11.1). LLM only at the edges: tool selection + narration.
Claim -> Principal -> rate limit -> normalize -> (button: deterministic | text: router) -> tool -> narrate -> number guard -> send."""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..agents import team as T
from ..agents.orion import ORION_SYSTEM, Step, plan_schema, single_step, validate_plan
from ..config import Settings
from ..crm.hubspot.writeback import HubSpotWriter
from ..insights import spec
from ..llm import prompts
from ..llm.base import LlmClient, LlmError, Usage
from ..llm.guard import numbers_ok
from ..llm.transcribe import TranscribeError, Transcriber
from ..security.pii_masking import mask_pii
from ..security.principal import Principal, resolve_by_phone
from . import actions, repo
from . import strings_ptbr as S
from .actions import Reply, audit
from .gateway import GatewayError, MessagingGateway
from .router import keyword_args, keyword_route
from .tools import catalog

log = logging.getLogger("omnidata.orchestrator")
Conn = psycopg.Connection[Any]
CONSENT_VERSION = "v1"


@dataclass
class Deps:
    gateway: MessagingGateway
    writer: HubSpotWriter | None
    llm: LlmClient | None
    settings: Settings
    transcriber: Transcriber | None = None
    today: date | None = None


# ---------------- queue -----------------
def claim_next(conn: Conn) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("update app.wa_message set status='processing', attempts=attempts+1 where id = ("
                    "select id from app.wa_message where direction='in' and status in ('received') "
                    "order by received_at for update skip locked limit 1) returning *")
        row = cur.fetchone()
    conn.commit()
    return row


def requeue_stuck(conn: Conn) -> int:
    with conn.cursor() as cur:
        cur.execute("update app.wa_message set status = case when attempts >= 3 then 'failed' else 'received' end "
                    "where direction='in' and status='processing' and received_at < now() - interval '2 minutes'")
        n = cur.rowcount
    conn.commit()
    return n


async def process_next(conn: Conn, deps: Deps) -> bool:
    msg = claim_next(conn)
    if not msg:
        return False
    try:
        await handle(conn, deps, msg)
        status, err = "done", None
    except Exception as exc:  # never lose a message silently
        conn.rollback()
        log.error("message failed: %s", type(exc).__name__)
        status, err = ("failed" if msg["attempts"] >= 3 else "received"), type(exc).__name__
    with conn.cursor() as cur:
        cur.execute("update app.wa_message set status=%s, error=%s, processed_at=now() where id=%s", (status, err, msg["id"]))
    conn.commit()
    return True


# ---------------- sending -----------------
async def send(conn: Conn, deps: Deps, to: str, user_id: str | None, reply: Reply) -> None:
    if reply.list_rows:
        await deps.gateway.send_list(to, reply.text, reply.list_button, reply.list_rows)
        kind = "list"
    elif reply.buttons:
        await deps.gateway.send_buttons(to, reply.text, reply.buttons[:3])
        kind = "buttons"
    else:
        await deps.gateway.send_text(to, reply.text)
        kind = "text"
    with conn.cursor() as cur:
        cur.execute("insert into app.wa_message (user_id, direction, kind, payload, status, processed_at) values (%s,'out',%s,%s,'done',now())",
                    (user_id, kind, Jsonb({"len": len(reply.text)})))  # never store bodies for outbound either
    conn.commit()


def _log_llm(conn: Conn, user_id: str, purpose: str, u: Usage) -> None:
    if u.provider == "none":
        return
    with conn.cursor() as cur:
        cur.execute("insert into app.llm_call (user_id, purpose, provider, model, input_tokens, output_tokens, latency_ms) values (%s,%s,%s,%s,%s,%s,%s)",
                    (user_id, purpose, u.provider, u.model, u.input_tokens, u.output_tokens, u.latency_ms))
    conn.commit()


def _over_budget(conn: Conn, p: Principal, s: Settings) -> bool:
    with conn.cursor() as cur:
        cur.execute("select coalesce(sum(input_tokens + output_tokens),0) t from app.llm_call where user_id=%s and created_at >= date_trunc('day', now())", (p.user_id,))
        return int(cur.fetchone()["t"]) >= s.user_daily_token_budget


def _rate_limited(conn: Conn, phone: str, s: Settings) -> bool:
    with conn.cursor() as cur:  # keyed by sender number (payload), not user_id, so it also holds for unresolved senders
        cur.execute("select count(*) n from app.wa_message where direction='in' and payload->>'from' = %s and received_at > now() - interval '1 hour'", (phone,))
        return int(cur.fetchone()["n"]) > s.rate_limit_msgs_per_hour


# ---------------- conversation state -----------------
def _get_state(conn: Conn, p: Principal) -> tuple[str, dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("select state, context from app.conversation_state where user_id=%s and (expires_at is null or expires_at > now())", (p.user_id,))
        r = cur.fetchone()
    return (r["state"], r["context"]) if r else ("idle", {})


def _set_state(conn: Conn, p: Principal, state: str, ctx: dict[str, Any] | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into app.conversation_state (user_id, state, context, updated_at, expires_at) values (%s,%s,%s,now(), now() + interval '30 minutes') "
                    "on conflict (user_id) do update set state=excluded.state, context=excluded.context, updated_at=now(), expires_at=excluded.expires_at",
                    (p.user_id, state, Jsonb(ctx or {})))
    conn.commit()


# ---------------- entrypoint -----------------
async def handle(conn: Conn, deps: Deps, msg: dict[str, Any]) -> None:
    body = msg["payload"]
    phone = body["from"]
    p = resolve_by_phone(conn, phone)
    if p is None:
        await _onboarding_or_refuse(conn, deps, phone, body)
        return
    if _rate_limited(conn, phone, deps.settings):
        await send(conn, deps, phone, p.user_id, Reply(S.RATE_LIMITED))
        return

    kind = msg["kind"]
    if kind == "interactive":
        reply = await _handle_reply_id(conn, deps, p, body["reply_id"])
    elif kind in ("text", "audio"):
        text = body.get("text", "")
        heard = ""
        if kind == "audio":
            text, err = await _transcribe(conn, deps, p, body)
            if err:
                await send(conn, deps, phone, p.user_id, Reply(err))
                return
            heard = S.HEARD.format(t=text[:200])  # show what was understood: transcription can be wrong, writes are risky
        reply = await _handle_text(conn, deps, p, text)
        if heard:
            reply.text = f"{heard}\n\n{reply.text}"
    else:
        reply = Reply(S.MENU_BODY, list_rows=[(f"menu:{k}", t, d) for k, t, d in S.MENU_ROWS], list_button=S.MENU_TITLE[:20])
    await send(conn, deps, phone, p.user_id, reply)


async def _transcribe(conn: Conn, deps: Deps, p: Principal, body: dict[str, Any]) -> tuple[str, str | None]:
    """Voice note -> text. Returns (text, None) or ("", user-facing error). Cost is logged per user (app.llm_call)."""
    if not deps.transcriber:
        return "", S.AUDIO_FAIL
    with conn.cursor() as cur:
        cur.execute("select coalesce(sum(cost_usd),0) c from app.llm_call where user_id=%s and purpose='transcribe' "
                    "and created_at >= date_trunc('day', now())", (p.user_id,))
        spent = float(cur.fetchone()["c"])
    conn.commit()
    if spent >= deps.settings.transcribe_daily_budget_usd:
        return "", S.AUDIO_BUDGET
    try:
        audio, mime = await deps.gateway.download_media(body["media_id"])
        t = await deps.transcriber.transcribe(audio, mime)
    except TranscribeError as exc:
        audit(conn, p.user_id, "transcribe_failed", {"code": exc.code})
        conn.commit()
        if exc.code == "too_long":
            return "", S.AUDIO_TOO_LONG.format(max=deps.settings.transcribe_max_seconds)
        return "", S.AUDIO_TOO_BIG if exc.code == "too_big" else S.AUDIO_FAIL
    except GatewayError:
        return "", S.AUDIO_FAIL
    with conn.cursor() as cur:
        cur.execute("insert into app.llm_call (user_id, purpose, provider, model, cost_usd, latency_ms) values (%s,'transcribe','openai',%s,%s,%s)",
                    (p.user_id, t.model, t.cost_usd, t.latency_ms))
    conn.commit()
    return (t.text, None) if t.text else ("", S.AUDIO_EMPTY)


async def _onboarding_or_refuse(conn: Conn, deps: Deps, phone: str, body: dict[str, Any]) -> None:
    """FR-BOT-1: only an invited user replying 'Aceito' is activated; everyone else gets a fixed refusal and NO data."""
    txt = (body.get("text") or body.get("title") or "").strip().lower()
    with conn.cursor() as cur:
        cur.execute("select id, display_name from app.app_user where phone_e164=%s and status='invited'", (phone,))
        u = cur.fetchone()
        if u and txt in ("aceito", "aceitar"):
            cur.execute("update app.app_user set status='active', opted_in_at=now(), consent_text_version=%s where id=%s", (CONSENT_VERSION, u["id"]))
            conn.commit()
            audit(conn, str(u["id"]), "opt_in", {"consent_text_version": CONSENT_VERSION})
            conn.commit()
            await send(conn, deps, phone, str(u["id"]), Reply(S.ONBOARDING_OK.format(name=u["display_name"] or "")))
            return
        conn.commit()
    await send(conn, deps, phone, str(u["id"]) if u else None, Reply(S.ONBOARDING_ASK if u else S.REFUSAL_UNKNOWN))


# ---------------- deterministic handler for buttons/lists (no LLM) -----------------
async def _handle_reply_id(conn: Conn, deps: Deps, p: Principal, rid: str) -> Reply:
    parts = rid.split(":")
    today = deps.today or datetime.now(UTC).date()
    if parts[0] == "menu":
        tool = {"kpis": "get_kpis", "quota": "get_quota_status", "pipeline": "get_pipeline_summary",
                "attention": "list_deals_needing_action", "brief": "get_morning_brief"}.get(parts[1])
        return await _run_tool(conn, deps, p, tool, {}) if tool else Reply(S.NO_DATA)
    if parts[0] == "pick" and len(parts) == 2:  # disambiguation answer: run the remembered intent on the chosen deal
        state, ctx = _get_state(conn, p)
        _set_state(conn, p, "idle")
        deal = repo.get_deal_scoped(conn, p, parts[1])
        if not deal:
            return Reply(S.NO_DATA)
        if state == "pick" and ctx.get("tool"):
            return _sign(T.agent_for_tool(ctx["tool"]), await _run_write_with_deal(conn, deps, p, ctx["tool"], ctx["args"], deal["hs_deal_id"]))
        return Reply(S.tpl_deal(_deal_view(deal)))
    if parts[0] == "act" and len(parts) == 3:
        verb, ident = parts[1], parts[2]
        if verb == "confirm" and deps.writer:
            return await actions.confirm(conn, deps.writer, p, ident)
        if verb == "cancel":
            return actions.cancel(conn, p, ident)
        if verb == "undo" and deps.writer:
            return await actions.undo(conn, deps.writer, p, ident)
        if verb == "adjust":
            actions.cancel(conn, p, ident)
            a = actions._own_action(conn, p, ident)
            conn.commit()
            if a:
                _set_state(conn, p, "adjust", {"deal_id": a["params"]["deal_id"], "field": a["params"]["field"]})
                return Reply("Certo. Diga o novo valor.")
        if verb == "edit":
            _set_state(conn, p, "edit", {"action_id": ident})
            return Reply("Ok. Mande o novo texto.")
        if verb == "snooze":
            with conn.cursor() as cur:
                cur.execute("update app.alert_event set snoozed_until = now() + interval '3 days' where user_id=%s and hs_deal_id = "
                            "(select hs_deal_id from app.alert_event where id=%s and user_id=%s)", (p.user_id, ident, p.user_id))
            conn.commit()
            return Reply(S.SNOOZED)
        if verb == "open":
            with conn.cursor() as cur:
                cur.execute("update app.alert_event set viewed_at = now() where id::text=%s and user_id=%s and viewed_at is null", (ident, p.user_id))
            conn.commit()
            if ident == "brief":
                return await _run_tool(conn, deps, p, "get_morning_brief", {})
            with conn.cursor() as cur:
                cur.execute("select hs_deal_id from app.alert_event where id::text=%s and user_id=%s", (ident, p.user_id))
                r = cur.fetchone()
            deal = repo.get_deal_scoped(conn, p, r["hs_deal_id"]) if r else None
            return Reply(S.tpl_deal(_deal_view(deal))) if deal else Reply(S.NO_DATA)
    _ = today
    return Reply(S.MENU_BODY, list_rows=[(f"menu:{k}", t, d) for k, t, d in S.MENU_ROWS], list_button=S.MENU_TITLE[:20])


def _deal_view(d: dict[str, Any]) -> dict[str, Any]:
    return {"name": d["name"], "stage": d["stage_label"], "amount": float(d["amount"] or 0),
            "days_in_stage": float(d["days_in_stage"]), "flags": list(d["health_flags"])}


# ---------------- free text -----------------
async def _handle_text(conn: Conn, deps: Deps, p: Principal, text: str) -> Reply:
    text = text.strip()
    low = text.lower()
    if low in ("pode", "confirmo", "confirmar", "sim") or low in ("cancela", "cancelar", "não", "nao"):
        return await _free_text_confirmation(conn, deps, p, confirm=low in ("pode", "confirmo", "confirmar", "sim"))
    state, ctx = _get_state(conn, p)
    if state == "adjust":
        _set_state(conn, p, "idle")
        return actions.propose_deal_update(conn, p, "", ctx["field"], text, deal_id=ctx["deal_id"])
    if state == "edit" and deps.writer:
        _set_state(conn, p, "idle")
        return await actions.edit_receipt(conn, deps.writer, p, ctx["action_id"], text)

    return await _orion(conn, deps, p, text)


def _menu() -> Reply:
    return Reply(S.MENU_BODY, list_rows=[(f"menu:{k}", t, d) for k, t, d in S.MENU_ROWS], list_button=S.MENU_TITLE[:20])


def _sign(agent: T.Agent, r: Reply) -> Reply:
    r.text = f"*{agent.name}*: {r.text}"
    return r


_NICK = re.compile(r"^\s*me chama de\s+(.{1,30}?)\s*[.!]?\s*$", re.IGNORECASE)
_TEAM_Q = re.compile(r"\b(equipe|quem (sao|são) (voces|vocês)|quem trabalha|observatorio|observatório)\b", re.IGNORECASE)


async def _orion(conn: Conn, deps: Deps, p: Principal, text: str) -> Reply:
    """Orion analyses the request and routes it to the specialists (ADR 0003). Falls back to keywords when there is no LLM."""
    m = _NICK.match(text)
    if m:  # 'me chama de Rê' (assessor-style preference by message)
        nick = mask_pii(m.group(1)).strip()
        with conn.cursor() as cur:
            cur.execute("update app.app_user set display_name=%s where id=%s", (nick, p.user_id))
        conn.commit()
        return _sign(T.ORION, Reply(S.NICK_OK.format(nick=nick)))
    forced: T.Agent | None = None
    addr = T.parse_address(text)
    if addr:
        forced, text = addr
        if not text or text.lower().strip("?!. ") in ("quem é você", "quem e voce", "oi", "olá", "ola"):
            return _sign(forced, Reply(S.AGENT_INTRO.format(name=forced.name, title=forced.title, tagline=forced.tagline, example=forced.examples[0])))
    if forced is None and _TEAM_Q.search(text):
        return _sign(T.ORION, Reply(S.tpl_team([(a.name, a.title, a.tagline) for a in T.TEAM.values()])))

    steps: list[Step] | None = None
    if deps.llm and not _over_budget(conn, p, deps.settings):
        try:
            res = await deps.llm.route(ORION_SYSTEM, mask_pii(text), [plan_schema()])
            _log_llm(conn, p.user_id, "planner", res.usage)
            if res.tool and res.tool.name == "plan":
                steps = validate_plan(res.tool.arguments.get("steps"), forced)
                if steps is None:
                    _log_step(conn, p, "orion", "plan", "rejected", 0)  # invalid plan: never executed
            elif res.tool and res.tool.name in T.TOOL_OWNER:  # single direct tool call (also accepted)
                steps = validate_plan([{"agent": T.TOOL_OWNER[res.tool.name], "tool": res.tool.name, "args": res.tool.arguments}], forced)
            elif res.text and "FORA_DO_ESCOPO" in res.text:
                return _sign(T.ORION, Reply(S.OUT_OF_SCOPE))
        except LlmError:
            audit(conn, p.user_id, "llm_down", {})
            conn.commit()
    if steps is None:
        tool = keyword_route(text)  # degraded mode (FR-BOT-7): one specialist, no LLM
        if tool is None and forced is None and _INSIGHTS_Q.search(text):
            # "me dá os insights": Orion splits it (Lyra: dores, Altair: demanda, Argus: cobertura)
            return await run_plan(conn, deps, p, validate_plan(OVERVIEW_PLAN) or [], text)
        if tool is None:
            return _menu()
        if forced and T.TOOL_OWNER[tool] != forced.key:
            owner = T.TEAM[T.TOOL_OWNER[tool]]
            return _sign(forced, Reply(S.NOT_MINE.format(other=owner.name, title=owner.title, hint=owner.examples[0].split(", ")[-1].strip("“”\""))))
        steps = single_step(tool, keyword_args(tool, text))
    return await run_plan(conn, deps, p, steps, text)


def _log_step(conn: Conn, p: Principal, agent: str, tool: str, status: str, ms: int, run_id: str | None = None, n: int = 0) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into app.agent_step (run_id, step_no, user_id, agent, tool, status, latency_ms) values (%s,%s,%s,%s,%s,%s,%s)",
                    (run_id or str(uuid.uuid4()), n, p.user_id, agent, tool, status, ms))
    conn.commit()


async def run_plan(conn: Conn, deps: Deps, p: Principal, steps: list[Step], original_text: str = "") -> Reply:
    """Sequential, bounded execution: each step is one specialist calling one allowed tool. Orion merges into ONE reply."""
    import time
    import uuid
    run_id = str(uuid.uuid4())
    parts: list[str] = []
    last = Reply("")
    for i, st in enumerate(steps):
        t0 = time.monotonic()
        try:
            r = await _run_tool(conn, deps, p, st.tool, st.args, original_text)
            status = "ok"
        except Exception:
            conn.rollback()
            _log_step(conn, p, st.agent, st.tool, "failed", int((time.monotonic() - t0) * 1000), run_id, i)
            raise
        _log_step(conn, p, st.agent, st.tool, "ok", int((time.monotonic() - t0) * 1000), run_id, i)
        _ = status
        if r.list_rows:  # a specialist needs the user to pick something: stop the plan here
            return Reply("\n\n".join([*parts, r.text]), list_rows=r.list_rows, list_button=r.list_button)
        parts.append(r.text)
        last = r
    return Reply("\n\n".join(parts), buttons=last.buttons)


async def _free_text_confirmation(conn: Conn, deps: Deps, p: Principal, confirm: bool) -> Reply:
    """'pode' / 'cancela' are equivalent to the buttons (FR-WRT-2)."""
    with conn.cursor() as cur:
        cur.execute("select id from app.pending_action where user_id=%s and status='proposed' and expires_at > now() order by created_at desc limit 1", (p.user_id,))
        r = cur.fetchone()
    conn.commit()
    if not r:
        return Reply(S.MENU_BODY, list_rows=[(f"menu:{k}", t, d) for k, t, d in S.MENU_ROWS], list_button=S.MENU_TITLE[:20])
    if confirm and deps.writer:
        return await actions.confirm(conn, deps.writer, p, str(r["id"]))
    return actions.cancel(conn, p, str(r["id"]))


async def _run_tool(conn: Conn, deps: Deps, p: Principal, tool: str | None, args: dict[str, Any], original_text: str = "") -> Reply:
    reply = await _run_tool_raw(conn, deps, p, tool, args, original_text)
    return _sign(T.agent_for_tool(tool), reply) if tool and reply.text else reply


async def _run_tool_raw(conn: Conn, deps: Deps, p: Principal, tool: str | None, args: dict[str, Any], original_text: str = "") -> Reply:
    if not tool:
        return Reply(S.NO_DATA)
    parsed = catalog.validate(tool, args)
    if parsed is None:
        return Reply(S.MENU_BODY, list_rows=[(f"menu:{k}", t, d) for k, t, d in S.MENU_ROWS], list_button=S.MENU_TITLE[:20])
    today = deps.today or datetime.now(UTC).date()
    a = parsed.model_dump()
    if tool in catalog.READ_TOOLS:
        data, template = _read(conn, p, tool, a, today)
        if data is None:
            return Reply(S.NO_MATCH_DEAL.format(q=a.get("query", "")))
        return Reply(await _narrate(conn, deps, p, data, template, T.agent_for_tool(tool)))
    if not deps.writer:
        return Reply(S.HUBSPOT_DOWN)
    if tool == "undo_last":
        with conn.cursor() as cur:
            cur.execute("select id from app.pending_action where user_id=%s and status='executed' and undo_deadline > now() order by executed_at desc limit 1", (p.user_id,))
            r = cur.fetchone()
        conn.commit()
        return await actions.undo(conn, deps.writer, p, str(r["id"])) if r else Reply(S.ALREADY_DONE)
    return await _run_write(conn, deps, p, tool, a)


def _read(conn: Conn, p: Principal, tool: str, a: dict[str, Any], today: date):  # type: ignore[no-untyped-def]
    if tool == "get_kpis":
        return repo.kpis(conn, p, repo.month_start(today, a["period"])), S.tpl_kpis
    if tool == "get_quota_status":
        return repo.quota_status(conn, p, repo.month_start(today, a["period"])), S.tpl_quota
    if tool == "get_pipeline_summary":
        return repo.pipeline_summary(conn, p), S.tpl_pipeline
    if tool == "list_deals_needing_action":
        return repo.deals_needing_action(conn, p, a["limit"]), S.tpl_attention
    if tool == "get_morning_brief":
        d = {"name": p.display_name, "quota": repo.quota_status(conn, p, repo.month_start(today)),
             "attention": repo.deals_needing_action(conn, p, 5)}
        return d, S.tpl_brief
    if tool == "get_data_quality":
        return repo.data_quality(conn, p), S.tpl_quality
    if tool in INSIGHT_TOOLS:
        return _insight(conn, p, tool, a)
    if tool == "get_fix_queue":
        return repo.fix_queue(conn, p, int(a.get("limit", 5))), S.tpl_fix_queue
    if tool == "get_deal":
        found = repo.find_deals(conn, p, a["query"], 1)
        return (_deal_view(found[0]), S.tpl_deal) if found else (None, S.tpl_deal)
    return None, S.tpl_deal


INSIGHT_TOOLS = {"get_pains", "get_recurring_terms", "get_demand_types", "get_systems_landscape", "get_segment_insights",
                 "get_insight_coverage", "get_insight_digest"}


def _insight(conn: Conn, p: Principal, tool: str, a: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    """Company insights (dores, termos, ERPs, demanda, outros). One deterministic analysis, one section per tool."""
    lim = int(a.get("limit", 6))
    an = repo.insight_analysis(conn, p, 10)
    cov = an["coverage"]
    if tool == "get_pains":
        return {"deals": cov["deals"], "with_pain": an["pains"]["with_pain"], "low_n": an["pains"]["low_n"], "items": an["pains"]["items"][:lim]}, S.tpl_pains
    if tool == "get_recurring_terms":
        return {"deals": cov["deals"], "words": an["terms"]["words"][:lim], "phrases": an["terms"]["phrases"][:lim]}, S.tpl_terms
    if tool == "get_demand_types":
        return {"total": an["demand_types"]["total"], "items": an["demand_types"]["items"][:lim]}, S.tpl_demand
    if tool == "get_systems_landscape":
        cat = a.get("category", "all")
        return {"category": cat, "items": (an["systems"]["items"] if cat == "all" else an["systems"][cat])[:lim]}, S.tpl_systems
    if tool == "get_segment_insights":
        dim = a.get("dimension", "segment")
        if dim == "loss_reason":
            return {"dimension": dim, "lost": an["loss_reasons"]["lost"], "items": an["loss_reasons"]["taxonomy"][:lim]}, S.tpl_segments
        return {"dimension": dim, "min_segment_deals": spec.MIN_SEGMENT_DEALS, "items": an["segments" if dim == "segment" else "campaigns"]["items"][:lim]}, S.tpl_segments
    if tool == "get_insight_coverage":
        return cov, S.tpl_coverage
    def top(k: str, sub: str) -> Any:
        return an[k][sub][0] if an[k][sub] else None
    return {"pain": None if an["pains"]["low_n"] else top("pains", "items"), "pains_recorded": an["pains"]["with_pain"], "demand": top("demand_types", "items"), "system": top("systems", "items")}, S.tpl_digest


_INSIGHTS_Q = re.compile(r"\b(insights?|panorama das empresas|radar das empresas)\b", re.IGNORECASE)
OVERVIEW_PLAN = [{"agent": "lyra", "tool": "get_pains", "args": {}}, {"agent": "altair", "tool": "get_demand_types", "args": {}},
                 {"agent": "argus", "tool": "get_insight_coverage", "args": {}}]


async def _narrate(conn: Conn, deps: Deps, p: Principal, data: dict[str, Any], template: Any, agent: T.Agent | None = None) -> str:
    """Narrator LLM sees tool JSON only; number guard decides whether its text may be sent (§11.3)."""
    fallback: str = template(data)
    if not deps.llm or _over_budget(conn, p, deps.settings):
        return fallback
    payload = json.dumps(data, default=str, ensure_ascii=False)
    try:
        persona = f" Você é {agent.name}, {agent.title}. {agent.persona}" if agent else ""
        text, usage = await deps.llm.narrate(prompts.NARRATOR_SYSTEM + persona, payload)
        _log_llm(conn, p.user_id, "narrator", usage)
    except LlmError:
        return fallback
    if text and len(text) <= 600 and numbers_ok(text, json.loads(payload)):
        return text
    audit(conn, p.user_id, "number_guard_fallback", {"agent": agent.key if agent else None})
    conn.commit()
    return fallback


async def _run_write(conn: Conn, deps: Deps, p: Principal, tool: str, a: dict[str, Any]) -> Reply:
    assert deps.writer
    found = repo.find_deals(conn, p, a["deal"])
    if len(found) > 1 and found[0]["name"].lower() != a["deal"].lower():  # ambiguity -> list message, remember intent
        _set_state(conn, p, "pick", {"tool": tool, "args": a})
        rows = [(f"pick:{d['hs_deal_id']}", d["name"], f"{d['stage_label']} · {S.brl(d['amount'])}") for d in found[:10]]
        return Reply(S.PICK_DEAL, list_rows=rows)
    deal_id = found[0]["hs_deal_id"] if found else None
    if deal_id is None:
        return Reply(S.NO_MATCH_DEAL.format(q=a["deal"]))
    return await _run_write_with_deal(conn, deps, p, tool, a, deal_id)


async def _run_write_with_deal(conn: Conn, deps: Deps, p: Principal, tool: str, a: dict[str, Any], deal_id: str) -> Reply:
    assert deps.writer
    if tool == "add_note":
        return await actions.add_note(conn, deps.writer, p, a["deal"], a["text"], deal_id=deal_id)
    if tool == "create_task":
        return await actions.create_task(conn, deps.writer, p, a["deal"], a["title"], a.get("due_in_days", 1), deal_id=deal_id)
    if tool == "propose_deal_update":
        return actions.propose_deal_update(conn, p, a["deal"], a["field"], a["value"], deal_id=deal_id)
    return Reply(S.NO_DATA)
