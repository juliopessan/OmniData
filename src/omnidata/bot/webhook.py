"""Evolution API webhook (§11.1 step 1, ADR 0008): verify the shared secret, persist, return 200 fast. No processing here.
No native request signature (unlike Meta's HMAC): the secret is a custom header WE configured via
EvolutionAdminClient.set_webhook (X-OmniData-Secret), checked constant-time in verify_evolution_secret."""
from __future__ import annotations

import json
import logging
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException, Request
from psycopg.types.json import Jsonb

from ..config import get_settings
from .evolution import verify_evolution_secret

log = logging.getLogger("omnidata.webhook")
router = APIRouter()
SECRET_HEADER = "x-omnidata-secret"


def normalize_phone(jid: str) -> str:
    """Evolution's remoteJid is '<number>@s.whatsapp.net' (or '@g.us' for groups, never routed to a Principal)."""
    return "+" + jid.split("@", 1)[0].lstrip("+")


def extract_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Evolution posts one event per call. `data` is usually a single object, but is handled as a list too in case
    a deployment batches upserts (OPEN-8: unverified against a real instance either way)."""
    if str(payload.get("event", "")).replace("_", ".").lower() != "messages.upsert":
        return []
    data = payload.get("data")
    return [d for d in (data if isinstance(data, list) else [data]) if isinstance(d, dict)]


def message_kind(d: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """None = not a kind we handle (system message, reaction, etc.) — persisted nowhere, logged as skipped only."""
    msg = d.get("message") or {}
    if "conversation" in msg:
        return "text", {"text": msg["conversation"]}
    if "extendedTextMessage" in msg:  # a text reply that quotes another message
        return "text", {"text": (msg["extendedTextMessage"] or {}).get("text", "")}
    if "audioMessage" in msg:
        return "audio", {"media_id": d.get("key", {}).get("id", ""), "mime": (msg["audioMessage"] or {}).get("mimetype", "audio/ogg")}
    if "buttonsResponseMessage" in msg:
        r = msg["buttonsResponseMessage"] or {}
        return "interactive", {"reply_id": r.get("selectedButtonId", ""), "title": r.get("selectedDisplayText", "")}
    if "listResponseMessage" in msg:
        r = (msg["listResponseMessage"] or {}).get("singleSelectReply", {})
        return "interactive", {"reply_id": r.get("selectedRowId", ""), "title": ""}
    return None


def persist_inbound(conn: psycopg.Connection[Any], payload: dict[str, Any]) -> int:
    """Insert each message once (wa_message_id is UNIQUE, so duplicate deliveries are ignored). Messages the bot itself
    sent come back through this same webhook (Baileys echoes fromMe:true) and must never be treated as inbound."""
    n = 0
    for d in extract_events(payload):
        key = d.get("key") or {}
        jid = key.get("remoteJid")
        if key.get("fromMe") or not key.get("id") or not jid:
            continue
        if str(jid).endswith("@g.us"):  # a group, never a seller DM — found live: the bot was replying in every group
            continue                    # the connected number belongs to, since nothing here ever checked this before
        parsed = message_kind(d)
        if parsed is None:
            continue
        kind, body = parsed
        body["from"] = normalize_phone(str(jid))
        with conn.cursor() as cur:
            cur.execute("select id from app.app_user where phone_e164 = %s", (body["from"],))
            u = cur.fetchone()
            cur.execute(
                "insert into app.wa_message (wa_message_id, user_id, direction, kind, payload) "
                "values (%s, %s, 'in', %s, %s) on conflict (wa_message_id) do nothing",
                (str(key["id"]), u["id"] if u else None, kind, Jsonb(body)))
            n += cur.rowcount
    conn.commit()
    return n


@router.post("/webhooks/evolution")
async def receive(request: Request, x_omnidata_secret: str | None = Header(None)) -> dict[str, str]:
    if not verify_evolution_secret(get_settings().evolution_webhook_secret, x_omnidata_secret):
        raise HTTPException(401, "bad secret")
    raw = await request.body()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "invalid json") from exc
    connect = request.app.state.connect  # injected so tests can point at a test DB
    with connect() as conn:
        stored = persist_inbound(conn, payload)
    log.info("webhook stored=%d", stored)  # never log bodies or numbers
    return {"status": "ok"}
