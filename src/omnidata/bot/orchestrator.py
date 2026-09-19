"""Deterministic orchestrator (D7, §11.1). LLM only at the edges: tool selection + narration.
Claim -> Principal -> rate limit -> normalize -> (button: deterministic | text: router) -> tool -> narrate -> number guard -> send."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..config import Settings
from ..crm.hubspot.writeback import HubSpotWriter
from ..llm import prompts
from ..llm.base import LlmClient, LlmError, Usage
from ..llm.guard import numbers_ok
from ..security.pii_masking import mask_pii
from ..security.principal import Principal, resolve_by_phone
from . import actions, repo
from . import strings_ptbr as S
from .actions import Reply, audit
from .gateway import GatewayError, MessagingGateway
from .router import keyword_route
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
        if kind == "audio":
            text = await _transcribe(deps, body)
            if not text:
                await send(conn, deps, phone, p.user_id, Reply("Não consegui entender o áudio. Pode escrever ou tentar de novo?"))
                return
        reply = await _handle_text(conn, deps, p, text)
    else:
        reply = Reply(S.MENU_BODY, list_rows=[(f"menu:{k}", t, d) for k, t, d in S.MENU_ROWS], list_button=S.MENU_TITLE[:20])
    await send(conn, deps, phone, p.user_id, reply)


async def _transcribe(deps: Deps, body: dict[str, Any]) -> str:
    if not deps.llm:
        return ""
    try:
        audio, mime = await deps.gateway.download_media(body["media_id"])
        return await deps.llm.transcribe(audio, mime)
    except (LlmError, GatewayError):
        return ""


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
            return await _run_write_with_deal(conn, deps, p, ctx["tool"], ctx["args"], deal["hs_deal_id"])
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

    tool, args = None, {}
    if deps.llm and not _over_budget(conn, p, deps.settings):
        try:
            res = await deps.llm.route(prompts.ROUTER_SYSTEM, mask_pii(text), catalog.schemas())
            _log_llm(conn, p.user_id, "router", res.usage)
            if res.tool:
                tool, args = res.tool.name, res.tool.arguments
            elif res.text and "FORA_DO_ESCOPO" in res.text:
                return Reply(S.OUT_OF_SCOPE)
        except LlmError:
            audit(conn, p.user_id, "llm_down", {})
            conn.commit()
    if tool is None:
        tool = keyword_route(text)  # degraded mode (FR-BOT-7)
    if tool is None:
        return Reply(S.MENU_BODY, list_rows=[(f"menu:{k}", t, d) for k, t, d in S.MENU_ROWS], list_button=S.MENU_TITLE[:20])
    return await _run_tool(conn, deps, p, tool, args, original_text=text)


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
        return Reply(await _narrate(conn, deps, p, data, template))
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
    if tool == "get_deal":
        found = repo.find_deals(conn, p, a["query"], 1)
        return (_deal_view(found[0]), S.tpl_deal) if found else (None, S.tpl_deal)
    return None, S.tpl_deal


async def _narrate(conn: Conn, deps: Deps, p: Principal, data: dict[str, Any], template: Any) -> str:
    """Narrator LLM sees tool JSON only; number guard decides whether its text may be sent (§11.3)."""
    fallback: str = template(data)
    if not deps.llm or _over_budget(conn, p, deps.settings):
        return fallback
    payload = json.dumps(data, default=str, ensure_ascii=False)
    try:
        text, usage = await deps.llm.narrate(prompts.NARRATOR_SYSTEM, payload)
        _log_llm(conn, p.user_id, "narrator", usage)
    except LlmError:
        return fallback
    if text and len(text) <= 600 and numbers_ok(text, json.loads(payload)):
        return text
    audit(conn, p.user_id, "number_guard_fallback", {})
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
