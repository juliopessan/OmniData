"""MessagingGateway (D15). Meta WhatsApp Cloud API behind an interface so a BSP can replace it."""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Protocol

import httpx

GRAPH = "https://graph.facebook.com/v21.0"
MAX_BUTTONS, BTN_TITLE, BODY_MAX, ROWS_MAX, ROW_TITLE, ROW_DESC, TEXT_MAX = 3, 20, 1024, 10, 24, 72, 4096


class GatewayError(RuntimeError):
    pass


class MessagingGateway(Protocol):
    async def send_text(self, to: str, body: str) -> str: ...
    async def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> str: ...
    async def send_list(self, to: str, body: str, button: str, rows: list[tuple[str, str, str]]) -> str: ...
    async def send_template(self, to: str, name: str, params: list[str], quick_reply_payload: str | None = None) -> str: ...
    async def download_media(self, media_id: str) -> tuple[bytes, str]: ...


def verify_signature(app_secret: str, raw_body: bytes, header: str | None) -> bool:
    """X-Hub-Signature-256 = 'sha256=' + HMAC-SHA256(app_secret, raw body). Constant-time compare."""
    if not header or not header.startswith("sha256=") or not app_secret:
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def build_buttons(body: str, buttons: list[tuple[str, str]]) -> dict[str, Any]:
    """buttons = [(id, title)]. Enforces WhatsApp limits (max 3, title <= 20, body <= 1024)."""
    if not 1 <= len(buttons) <= MAX_BUTTONS:
        raise GatewayError("reply buttons: 1 to 3 allowed")
    return {"type": "button", "body": {"text": body[:BODY_MAX]}, "action": {"buttons": [
        {"type": "reply", "reply": {"id": i, "title": t[:BTN_TITLE]}} for i, t in buttons]}}


def build_list(body: str, button: str, rows: list[tuple[str, str, str]]) -> dict[str, Any]:
    if not 1 <= len(rows) <= ROWS_MAX:
        raise GatewayError("list messages: 1 to 10 rows allowed")
    return {"type": "list", "body": {"text": body[:BODY_MAX]}, "action": {"button": button[:BTN_TITLE], "sections": [
        {"title": "Opções", "rows": [{"id": i, "title": t[:ROW_TITLE], "description": d[:ROW_DESC]} for i, t, d in rows]}]}}


class WhatsAppCloudGateway:
    def __init__(self, phone_number_id: str, access_token: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._pid = phone_number_id
        self._http = httpx.AsyncClient(transport=transport, timeout=20.0,
                                       headers={"Authorization": f"Bearer {access_token}"})

    async def _send(self, payload: dict[str, Any]) -> str:
        try:
            r = await self._http.post(f"{GRAPH}/{self._pid}/messages", json={"messaging_product": "whatsapp", **payload})
        except httpx.TransportError as exc:
            raise GatewayError(f"transport: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise GatewayError(f"whatsapp {r.status_code}: {r.text[:160]}")
        return str(r.json().get("messages", [{}])[0].get("id", ""))

    async def send_text(self, to: str, body: str) -> str:
        return await self._send({"to": to.lstrip("+"), "type": "text", "text": {"body": body[:TEXT_MAX]}})

    async def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> str:
        return await self._send({"to": to.lstrip("+"), "type": "interactive", "interactive": build_buttons(body, buttons)})

    async def send_list(self, to: str, body: str, button: str, rows: list[tuple[str, str, str]]) -> str:
        return await self._send({"to": to.lstrip("+"), "type": "interactive", "interactive": build_list(body, button, rows)})

    async def send_template(self, to: str, name: str, params: list[str], quick_reply_payload: str | None = None) -> str:
        comps: list[dict[str, Any]] = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
        if quick_reply_payload:
            comps.append({"type": "button", "sub_type": "quick_reply", "index": "0",
                          "parameters": [{"type": "payload", "payload": quick_reply_payload}]})
        return await self._send({"to": to.lstrip("+"), "type": "template",
                                 "template": {"name": name, "language": {"code": "pt_BR"}, "components": comps}})

    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        meta = await self._http.get(f"{GRAPH}/{media_id}")
        if meta.status_code >= 400:
            raise GatewayError(f"media meta {meta.status_code}")
        info = meta.json()
        blob = await self._http.get(info["url"])
        if blob.status_code >= 400:
            raise GatewayError(f"media download {blob.status_code}")
        return blob.content, str(info.get("mime_type", "audio/ogg"))
