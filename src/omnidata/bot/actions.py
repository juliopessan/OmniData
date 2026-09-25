"""Writes (FR-WRT-1..5): pending_action + audit_log + idempotency; low-risk executes now, high-risk confirms first;
Undo is 24h with an optimistic check (D10); successful writes write through to silver."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..crm.hubspot.client import HubSpotError
from ..crm.hubspot.writeback import HubSpotWriter
from ..db import upsert
from ..mailer.gmail import EmailError, GmailSender
from ..proposals.pdf import render_pdf
from ..proposals.template import render_html
from ..security.principal import Principal
from . import repo
from . import strings_ptbr as S
from .gateway import GatewayError, MessagingGateway

Conn = psycopg.Connection[Any]
UNDO_WINDOW = timedelta(hours=24)
PENDING_TTL = timedelta(minutes=30)


@dataclass
class Reply:
    text: str
    buttons: list[tuple[str, str]] = field(default_factory=list)  # [(id, title)]
    list_rows: list[tuple[str, str, str]] = field(default_factory=list)
    list_button: str = "Escolher"


def audit(conn: Conn, user_id: str | None, event: str, detail: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into app.audit_log (user_id, event, detail) values (%s, %s, %s)", (user_id, event, Jsonb(detail)))


def _mark_alert_acted(conn: Conn, user_id: str, deal_id: str) -> None:
    with conn.cursor() as cur:  # FR-ALR-3: any write on that deal within 48h of the alert counts as acted
        cur.execute("update app.alert_event set acted_at = now() where user_id = %s and hs_deal_id = %s "
                    "and sent_at > now() - interval '48 hours' and acted_at is null", (user_id, deal_id))


def _new_pending(conn: Conn, p: Principal, kind: str, params: dict[str, Any], risk: str,
                 before: dict[str, Any] | None, status: str, ttl: timedelta | None) -> str:
    aid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute("insert into app.pending_action (id, user_id, kind, params, risk, status, idempotency_key, before_state, expires_at) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (aid, p.user_id, kind, Jsonb(params), risk, status, f"{p.user_id}:{aid}", Jsonb(before) if before else None,
                     datetime.now(UTC) + ttl if ttl else None))
    return aid


def _resolve_deal(conn: Conn, p: Principal, query: str) -> tuple[dict[str, Any] | None, Reply | None]:
    """One visible deal, or a Reply asking the user to pick / saying nothing matched."""
    found = repo.find_deals(conn, p, query)
    if not found:
        return None, Reply(S.NO_MATCH_DEAL.format(q=query))
    if len(found) > 1 and found[0]["name"].lower() != query.lower():
        rows = [(f"pick:{d['hs_deal_id']}", d["name"], f"{d['stage_label']} · {S.brl(d['amount'])}") for d in found[:10]]
        return None, Reply(S.PICK_DEAL, list_rows=rows, list_button="Escolher")
    return found[0], None


# ---------------- low-risk: note / task (execute now, receipt with Editar/Desfazer) -----------------
async def add_note(conn: Conn, w: HubSpotWriter, p: Principal, deal_query: str, text: str, *, deal_id: str | None = None) -> Reply:
    deal, ask = (repo.get_deal_scoped(conn, p, deal_id), None) if deal_id else _resolve_deal(conn, p, deal_query)
    if deal is None:
        return ask or Reply(S.NO_MATCH_DEAL.format(q=deal_query))
    aid = _new_pending(conn, p, "add_note", {"deal_id": deal["hs_deal_id"], "deal_name": deal["name"], "text": text}, "normal", None, "confirmed", None)
    conn.commit()
    try:
        note_id = await w.create_note(deal["hs_deal_id"], text, p.hs_owner_id)
    except HubSpotError:
        return _fail(conn, aid, p, "add_note")
    now = datetime.now(UTC)
    upsert(conn, "silver.activity", [{
        "hs_activity_id": f"note:{note_id}", "activity_type": "note", "hs_deal_id": deal["hs_deal_id"], "hs_contact_id": None,
        "hs_owner_id": p.hs_owner_id, "occurred_at": now, "due_at": None, "is_completed": None, "duration_sec": None,
        "direction": None, "outcome": None, "summary": text[:500], "transcript_path": None, "hs_updated_at": now}], ["hs_activity_id"])
    _executed(conn, aid, {"object_type": "notes", "object_id": note_id}, now)
    _mark_alert_acted(conn, p.user_id, deal["hs_deal_id"])
    audit(conn, p.user_id, "write_note", {"action_id": aid, "deal_id": deal["hs_deal_id"]})
    conn.commit()
    return Reply(S.receipt("note", deal["name"], text), buttons=[(f"act:edit:{aid}", S.BTN_EDIT), (f"act:undo:{aid}", S.BTN_UNDO)])


async def create_task(conn: Conn, w: HubSpotWriter, p: Principal, deal_query: str, title: str, due_in_days: int = 1, *,
                      deal_id: str | None = None) -> Reply:
    deal, ask = (repo.get_deal_scoped(conn, p, deal_id), None) if deal_id else _resolve_deal(conn, p, deal_query)
    if deal is None:
        return ask or Reply(S.NO_MATCH_DEAL.format(q=deal_query))
    due = (datetime.now(UTC) + timedelta(days=max(0, min(due_in_days, 365)))).replace(hour=12, minute=0, second=0, microsecond=0)
    aid = _new_pending(conn, p, "create_task", {"deal_id": deal["hs_deal_id"], "deal_name": deal["name"], "title": title,
                                                "due": due.isoformat()}, "normal", None, "confirmed", None)
    conn.commit()
    try:
        task_id = await w.create_task(deal["hs_deal_id"], title, due, p.hs_owner_id)
    except HubSpotError:
        return _fail(conn, aid, p, "create_task")
    now = datetime.now(UTC)
    upsert(conn, "silver.activity", [{
        "hs_activity_id": f"task:{task_id}", "activity_type": "task", "hs_deal_id": deal["hs_deal_id"], "hs_contact_id": None,
        "hs_owner_id": p.hs_owner_id, "occurred_at": None, "due_at": due, "is_completed": False, "duration_sec": None,
        "direction": None, "outcome": "NOT_STARTED", "summary": title, "transcript_path": None, "hs_updated_at": now}], ["hs_activity_id"])
    _executed(conn, aid, {"object_type": "tasks", "object_id": task_id}, now)
    _mark_alert_acted(conn, p.user_id, deal["hs_deal_id"])
    audit(conn, p.user_id, "write_task", {"action_id": aid, "deal_id": deal["hs_deal_id"]})
    conn.commit()
    return Reply(S.receipt("task", deal["name"], f"{title} (até {due:%d/%m})"),
                 buttons=[(f"act:edit:{aid}", S.BTN_EDIT), (f"act:undo:{aid}", S.BTN_UNDO)])


def _executed(conn: Conn, aid: str, after: dict[str, Any], now: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute("update app.pending_action set status='executed', after_state=%s, hs_response=%s, executed_at=%s, undo_deadline=%s "
                    "where id=%s", (Jsonb(after), Jsonb({"ok": True}), now, now + UNDO_WINDOW, aid))


def _fail(conn: Conn, aid: str, p: Principal, kind: str, message: str = S.HUBSPOT_DOWN) -> Reply:
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("update app.pending_action set status='failed', hs_response=%s where id=%s", (Jsonb({"ok": False}), aid))
    audit(conn, p.user_id, "write_failed", {"action_id": aid, "kind": kind})
    conn.commit()
    return Reply(message)  # never a silent success


# ---------------- high-risk: deal update (propose -> confirm) -----------------
def _coerce(conn: Conn, deal: dict[str, Any], field_name: str, value: str) -> tuple[dict[str, Any] | None, str | None]:
    """Returns ({hs_prop, hs_value, display_new, display_old, silver_col, silver_val}, error)."""
    if field_name == "amount":
        try:
            v = Decimal(value.replace("R$", "").replace(".", "").replace(",", ".").strip())
        except InvalidOperation:
            return None, "Não entendi o valor. Diga algo como 85000."
        return {"hs_prop": "amount", "hs_value": str(v), "new": S.brl(float(v)), "old": S.brl(float(deal["amount"] or 0)),
                "col": "amount", "val": v}, None
    if field_name == "close_date":
        try:
            d = datetime.fromisoformat(value[:10]).replace(tzinfo=UTC)
        except ValueError:
            return None, "Não entendi a data. Diga no formato AAAA-MM-DD."
        old = deal["close_date"].strftime("%d/%m/%Y") if deal.get("close_date") else "—"
        return {"hs_prop": "closedate", "hs_value": d.date().isoformat(), "new": d.strftime("%d/%m/%Y"), "old": old,
                "col": "close_date", "val": d}, None
    if field_name == "stage":
        with conn.cursor() as cur:  # stage metadata is silver (stable), scoped to the deal's own pipeline
            cur.execute("select hs_stage_id, label from silver.stage where hs_pipeline_id = %s and label ilike %s and not is_closed",
                        (deal["hs_pipeline_id"], f"%{value.strip()}%"))
            rows = cur.fetchall()
        if len(rows) != 1:
            return None, "Não achei essa etapa (ou achei mais de uma). Diga o nome exato da etapa."
        return {"hs_prop": "dealstage", "hs_value": rows[0]["hs_stage_id"], "new": rows[0]["label"], "old": deal["stage_label"],
                "col": "hs_stage_id", "val": rows[0]["hs_stage_id"]}, None
    return None, "Só consigo alterar etapa, data de fechamento ou valor."


def propose_deal_update(conn: Conn, p: Principal, deal_query: str, field_name: str, value: str, *, deal_id: str | None = None) -> Reply:
    deal, ask = (repo.get_deal_scoped(conn, p, deal_id), None) if deal_id else _resolve_deal(conn, p, deal_query)
    if deal is None:
        return ask or Reply(S.NO_MATCH_DEAL.format(q=deal_query))
    c, err = _coerce(conn, deal, field_name, value)
    if c is None:
        return Reply(err or S.NO_DATA)
    params = {"deal_id": deal["hs_deal_id"], "deal_name": deal["name"], "field": field_name, "hs_prop": c["hs_prop"],
              "hs_value": c["hs_value"], "new": c["new"], "old": c["old"], "col": c["col"], "val": str(c["val"])}
    aid = _new_pending(conn, p, "update_deal", params, "high", {"display": c["old"]}, "proposed", PENDING_TTL)
    conn.commit()
    return Reply(S.confirm_update(deal["name"], field_name, c["old"], c["new"]),
                 buttons=[(f"act:confirm:{aid}", S.BTN_CONFIRM), (f"act:adjust:{aid}", S.BTN_ADJUST), (f"act:cancel:{aid}", S.BTN_CANCEL)])


# ---------------- high-risk: send proposal (Vela; propose -> confirm, own confirm path) -----------------
def propose_send_proposal(conn: Conn, p: Principal, deal_query: str, summary: str, recipient_email: str, channel: str,
                          *, deal_id: str | None = None) -> Reply:
    deal, ask = (repo.get_deal_scoped(conn, p, deal_id), None) if deal_id else _resolve_deal(conn, p, deal_query)
    if deal is None:
        return ask or Reply(S.NO_MATCH_DEAL.format(q=deal_query))
    params = {"deal_id": deal["hs_deal_id"], "deal_name": deal["name"], "amount": str(deal["amount"] or 0),
              "summary": summary, "recipient_email": recipient_email, "channel": channel}
    aid = _new_pending(conn, p, "send_proposal", params, "high", None, "proposed", PENDING_TTL)
    conn.commit()
    where = {"email": f"por e-mail ({recipient_email})", "whatsapp": "aqui no WhatsApp", "both": f"por e-mail ({recipient_email}) e aqui no WhatsApp"}[channel]
    return Reply(f"Confirma o envio da proposta de *{deal['name']}* ({S.brl(deal['amount'])}) {where}?",
                 buttons=[(f"act:confirm:{aid}", S.BTN_CONFIRM), (f"act:cancel:{aid}", S.BTN_CANCEL)])


async def confirm_send_proposal(conn: Conn, p: Principal, aid: str, *, emailer: GmailSender | None, gateway: MessagingGateway) -> Reply:
    """Own confirm path — `confirm()` above is hard-coded to the HubSpot deal-update write, and this write never
    touches HubSpot at all (nothing to undo, so no undo_deadline/Undo button on the receipt either)."""
    with conn.cursor() as cur:
        cur.execute("update app.pending_action set status='confirmed' where id=%s and user_id=%s and status='proposed' "
                    "and expires_at > now() returning *", (aid, p.user_id))
        a = cur.fetchone()
    conn.commit()
    if not a:
        cur_a = _own_action(conn, p, aid)
        conn.commit()
        if cur_a and cur_a["status"] in ("executed", "confirmed"):
            return Reply(S.ALREADY_DONE)
        return Reply(S.EXPIRED)
    prm = a["params"]
    html = render_html(prm["deal_name"], S.brl(float(prm["amount"])), prm["summary"], p.display_name or "Vendedor")
    pdf = render_pdf(html)
    filename = f"proposta-{prm['deal_id']}.pdf"
    sent: list[str] = []
    try:
        if prm["channel"] in ("email", "both"):
            if not emailer:
                return _fail(conn, aid, p, "send_proposal", S.EMAIL_DOWN)
            await emailer.send(prm["recipient_email"], f"Proposta — {prm['deal_name']}",
                                f"Segue em anexo a proposta de {prm['deal_name']}.", attachment=(filename, pdf, "application/pdf"))
            sent.append("e-mail")
        if prm["channel"] in ("whatsapp", "both"):
            with conn.cursor() as cur:
                cur.execute("select phone_e164 from app.app_user where id=%s", (p.user_id,))
                phone = cur.fetchone()["phone_e164"]
            await gateway.send_document(phone, filename, pdf, "application/pdf", caption=f"Proposta: {prm['deal_name']}")
            sent.append("WhatsApp")
    except (EmailError, GatewayError):
        return _fail(conn, aid, p, "send_proposal", S.PROPOSAL_FAILED)
    now = datetime.now(UTC)
    _executed(conn, aid, {"sent_via": sent}, now)
    audit(conn, p.user_id, "send_proposal", {"action_id": aid, "deal_id": prm["deal_id"], "channel": prm["channel"]})
    conn.commit()
    return Reply(f"Enviado ✅ *{prm['deal_name']}*: proposta mandada via {' e '.join(sent)}.")


def _own_action(conn: Conn, p: Principal, aid: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("select * from app.pending_action where id = %s and user_id = %s", (aid, p.user_id))
        return cur.fetchone()


async def confirm(conn: Conn, w: HubSpotWriter, p: Principal, aid: str) -> Reply:
    """Atomic proposed->confirmed: pressing Confirm twice executes once (FR-WRT AC)."""
    with conn.cursor() as cur:
        cur.execute("update app.pending_action set status='confirmed' where id=%s and user_id=%s and status='proposed' "
                    "and expires_at > now() returning *", (aid, p.user_id))
        a = cur.fetchone()
    conn.commit()
    if not a:
        cur_a = _own_action(conn, p, aid)
        conn.commit()
        if cur_a and cur_a["status"] in ("executed", "confirmed"):
            return Reply(S.ALREADY_DONE)
        return Reply(S.EXPIRED)
    prm = a["params"]
    try:
        before = await w.get_deal_props(prm["deal_id"], [prm["hs_prop"]])
        await w.update_deal(prm["deal_id"], {prm["hs_prop"]: prm["hs_value"]})
    except HubSpotError:
        return _fail(conn, aid, p, "update_deal")
    now = datetime.now(UTC)
    col, val = prm["col"], prm["val"]
    with conn.cursor() as cur:  # write-through (FR-WRT-4)
        if col == "amount":
            cur.execute("update silver.deal set amount=%s, ingested_at=now() where hs_deal_id=%s", (Decimal(val), prm["deal_id"]))
        elif col == "close_date":
            cur.execute("update silver.deal set close_date=%s, ingested_at=now() where hs_deal_id=%s", (datetime.fromisoformat(val), prm["deal_id"]))
        else:
            cur.execute("update silver.deal set hs_stage_id=%s, ingested_at=now() where hs_deal_id=%s", (val, prm["deal_id"]))
    with conn.cursor() as cur:
        cur.execute("update app.pending_action set status='executed', before_state=%s, after_state=%s, hs_response=%s, executed_at=%s, "
                    "undo_deadline=%s where id=%s", (Jsonb({"hs_prop": prm["hs_prop"], "hs_value": before.get(prm["hs_prop"]), "display": prm["old"]}),
                                                    Jsonb({"hs_prop": prm["hs_prop"], "hs_value": prm["hs_value"]}), Jsonb({"ok": True}),
                                                    now, now + UNDO_WINDOW, aid))
    _mark_alert_acted(conn, p.user_id, prm["deal_id"])
    audit(conn, p.user_id, "write_deal_update", {"action_id": aid, "deal_id": prm["deal_id"], "field": prm["field"]})
    conn.commit()
    return Reply(f"Feito ✅ *{prm['deal_name']}*: {prm['old']} → *{prm['new']}*. Você pode *Desfazer* por 24h.",
                 buttons=[(f"act:undo:{aid}", S.BTN_UNDO)])


def cancel(conn: Conn, p: Principal, aid: str) -> Reply:
    with conn.cursor() as cur:
        cur.execute("update app.pending_action set status='cancelled' where id=%s and user_id=%s and status='proposed' returning id", (aid, p.user_id))
        ok = cur.fetchone()
    conn.commit()
    return Reply(S.CANCELLED if ok else S.ALREADY_DONE)


async def undo(conn: Conn, w: HubSpotWriter, p: Principal, aid: str) -> Reply:
    a = _own_action(conn, p, aid)
    conn.commit()
    if not a or a["status"] != "executed":
        return Reply(S.ALREADY_DONE)
    if a["undo_deadline"] and a["undo_deadline"] < datetime.now(UTC):
        return Reply(S.UNDO_EXPIRED)
    if a["kind"] not in ("add_note", "create_task", "update_deal"):
        return Reply(S.ALREADY_DONE)  # e.g. send_proposal: nothing to revert, already left the building
    try:
        if a["kind"] in ("add_note", "create_task"):
            await w.archive(a["after_state"]["object_type"], a["after_state"]["object_id"])
            with conn.cursor() as cur:
                cur.execute("delete from silver.activity where hs_activity_id = %s",
                            (f"{'note' if a['kind'] == 'add_note' else 'task'}:{a['after_state']['object_id']}",))
        else:  # optimistic check: only revert if CRM still holds the value WE wrote (D10)
            prop = a["after_state"]["hs_prop"]
            current = (await w.get_deal_props(a["params"]["deal_id"], [prop])).get(prop)
            if str(current) != str(a["after_state"]["hs_value"]) and not _same_value(prop, current, a["after_state"]["hs_value"]):
                return Reply(S.UNDO_STALE.format(current=current))
            await w.update_deal(a["params"]["deal_id"], {prop: a["before_state"]["hs_value"] or ""})
            _revert_silver(conn, a)
    except HubSpotError:
        return Reply(S.UNDO_FAILED)
    with conn.cursor() as cur:
        cur.execute("update app.pending_action set status='undone' where id=%s", (aid,))
    audit(conn, p.user_id, "undo", {"action_id": aid, "kind": a["kind"]})
    conn.commit()
    return Reply(S.UNDO_DONE)


def _same_value(prop: str, a: Any, b: Any) -> bool:
    try:
        return Decimal(str(a)) == Decimal(str(b)) if prop == "amount" else str(a)[:10] == str(b)[:10]
    except InvalidOperation:
        return False


def _revert_silver(conn: Conn, a: dict[str, Any]) -> None:
    prm, old = a["params"], a["before_state"].get("hs_value")
    with conn.cursor() as cur:
        if prm["col"] == "amount" and old not in (None, ""):
            cur.execute("update silver.deal set amount=%s where hs_deal_id=%s", (Decimal(str(old)), prm["deal_id"]))
        elif prm["col"] == "hs_stage_id" and old:
            cur.execute("update silver.deal set hs_stage_id=%s where hs_deal_id=%s", (old, prm["deal_id"]))
        elif prm["col"] == "close_date" and old:
            cur.execute("update silver.deal set close_date=%s where hs_deal_id=%s", (datetime.fromisoformat(str(old)[:10]).replace(tzinfo=UTC), prm["deal_id"]))


async def edit_receipt(conn: Conn, w: HubSpotWriter, p: Principal, aid: str, new_text: str) -> Reply:
    """'Editar' on a note/task receipt: the next message replaces the text."""
    a = _own_action(conn, p, aid)
    conn.commit()
    if not a or a["status"] != "executed" or a["kind"] not in ("add_note", "create_task"):
        return Reply(S.ALREADY_DONE)
    obj = a["after_state"]
    prop = "hs_note_body" if a["kind"] == "add_note" else "hs_task_subject"
    try:
        await w.update_object(obj["object_type"], obj["object_id"], {prop: new_text})
    except HubSpotError:
        return Reply(S.HUBSPOT_DOWN)
    with conn.cursor() as cur:
        cur.execute("update silver.activity set summary=%s where hs_activity_id=%s",
                    (new_text[:500], f"{'note' if a['kind'] == 'add_note' else 'task'}:{obj['object_id']}"))
        cur.execute("update app.pending_action set params = params || %s where id=%s", (Jsonb({"text" if a["kind"] == "add_note" else "title": new_text}), aid))
    audit(conn, p.user_id, "edit", {"action_id": aid})
    conn.commit()
    return Reply(S.receipt("note" if a["kind"] == "add_note" else "task", a["params"]["deal_name"], new_text),
                 buttons=[(f"act:edit:{aid}", S.BTN_EDIT), (f"act:undo:{aid}", S.BTN_UNDO)])


def expire_pending(conn: Conn) -> int:
    with conn.cursor() as cur:
        cur.execute("update app.pending_action set status='expired' where status='proposed' and expires_at < now()")
        n = cur.rowcount
    conn.commit()
    return n
