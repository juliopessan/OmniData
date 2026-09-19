"""WhatsApp webhook (§11.1 step 1): verify signature, persist, return 200 fast. No processing here."""
from __future__ import annotations

import json
import logging
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from psycopg.types.json import Jsonb

from ..config import get_settings
from .gateway import verify_signature

log = logging.getLogger("omnidata.webhook")
router = APIRouter()


def normalize_phone(wa_from: str) -> str:
    return "+" + wa_from.lstrip("+")


def extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Meta's entry/changes/value/messages nesting into [{id, from, type, body, ...}]."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for m in (change.get("value") or {}).get("messages", []) or []:
                out.append(m)
    return out


def message_kind(m: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    t = m.get("type")
    if t == "text":
        return "text", {"text": m["text"]["body"]}
    if t == "audio":
        return "audio", {"media_id": m["audio"]["id"], "mime": m["audio"].get("mime_type", "audio/ogg")}
    if t == "interactive":
        i = m["interactive"]
        r = i.get("button_reply") or i.get("list_reply") or {}
        return "interactive", {"reply_id": r.get("id", ""), "title": r.get("title", "")}
    if t == "button":  # template quick-reply
        return "interactive", {"reply_id": m["button"].get("payload", ""), "title": m["button"].get("text", "")}
    return "unsupported", {"type": t}


def persist_inbound(conn: psycopg.Connection[Any], payload: dict[str, Any]) -> int:
    """Insert each message once (wa_message_id is UNIQUE, so duplicate deliveries are ignored)."""
    n = 0
    for m in extract_messages(payload):
        kind, body = message_kind(m)
        body["from"] = normalize_phone(m["from"])
        with conn.cursor() as cur:
            cur.execute("select id from app.app_user where phone_e164 = %s", (body["from"],))
            u = cur.fetchone()
            cur.execute(
                "insert into app.wa_message (wa_message_id, user_id, direction, kind, payload) "
                "values (%s, %s, 'in', %s, %s) on conflict (wa_message_id) do nothing",
                (m["id"], u["id"] if u else None, kind, Jsonb(body)))
            n += cur.rowcount
    conn.commit()
    return n


@router.get("/webhooks/whatsapp")
async def verify(mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
                 challenge: str = Query("", alias="hub.challenge")) -> Response:
    expected = get_settings().whatsapp_verify_token
    if mode == "subscribe" and expected and token == expected:
        return Response(challenge, media_type="text/plain")
    raise HTTPException(403, "verification failed")


@router.post("/webhooks/whatsapp")
async def receive(request: Request, x_hub_signature_256: str | None = Header(None)) -> dict[str, str]:
    raw = await request.body()
    if not verify_signature(get_settings().whatsapp_app_secret, raw, x_hub_signature_256):
        raise HTTPException(401, "bad signature")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "invalid json") from exc
    connect = request.app.state.connect  # injected so tests can point at a test DB
    with connect() as conn:
        stored = persist_inbound(conn, payload)
    log.info("webhook stored=%d", stored)  # never log bodies or numbers
    return {"status": "ok"}
