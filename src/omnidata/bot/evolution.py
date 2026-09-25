"""Evolution API (self-hosted, Baileys/WhatsApp Web protocol) as the WhatsApp gateway (D15, ADR 0008 — replaces the
Meta Cloud API). Two roles:
  EvolutionAdminClient  instance lifecycle: create, QR code, connection state, webhook config, delete (§ pipeline setup).
  EvolutionGateway       the runtime MessagingGateway (send/receive) the bot uses once an instance is connected.

Endpoints and shapes below come from https://docs.evolutionfoundation.com.br (fetched 2026-09-22) plus a screenshot of
the user's own Evolution Manager (confirms channel=Baileys, an auto-generated instance token, and the dashboard flow).
NOT yet run against a real instance. Two things stay open until a real smoke test (OPEN-8, see ADR 0008):
  - the exact send-text and webhook-set request bodies (the public docs disagree with themselves across pages/versions);
  - the exact MESSAGES_UPSERT payload field names for text/audio (no example payload is published).
`send_text`/`extract_messages` are written defensively (try the documented shape, keep the raw payload either way) so a
field-name miss degrades to "no messages found" instead of a crash — never silently drops without a trace."""
from __future__ import annotations

import hmac
from typing import Any

import httpx

from .gateway import GatewayError

BUTTON_MAX = 3


def _as_dict(x: Any) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _as_list(x: Any) -> list[dict[str, Any]]:
    """fetchInstances answers either a bare array or {"instances": [...]}, depending on version."""
    if isinstance(x, list):
        return [i for i in x if isinstance(i, dict)]
    inner = _as_dict(x).get("instances")
    return [i for i in inner if isinstance(i, dict)] if isinstance(inner, list) else []


class EvolutionAdminClient:
    """Instance lifecycle (Evolution Manager's own UI does this by hand; this is the same calls, scripted).
    `api_key` is the server's global AUTHENTICATION_API_KEY — every documented endpoint accepts it."""

    def __init__(self, base_url: str, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._http = httpx.AsyncClient(transport=transport, timeout=30.0, headers={"apikey": api_key})

    async def _req(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        """Returns the parsed body as-is (dict for most endpoints, but fetchInstances may answer a bare array)."""
        try:
            r = await self._http.request(method, f"{self._base}{path}", json=json)
        except httpx.TransportError as exc:
            raise GatewayError(f"evolution transport: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise GatewayError(f"evolution {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    async def create_instance(self, name: str, *, number: str | None = None, webhook_url: str | None = None,
                              webhook_secret: str | None = None) -> dict[str, Any]:
        """Creates the instance and asks for a QR code in the same call (`qrcode: true`); the response already carries
        it (`qrcode.base64`) unless the instance was somehow left already-connected. `integration` picks Baileys
        (WhatsApp Web) over the "WHATSAPP-BUSINESS" (Cloud API relay) or generic "EVOLUTION" channels."""
        body: dict[str, Any] = {"instanceName": name, "qrcode": True, "integration": "WHATSAPP-BAILEYS"}
        if number:
            body["number"] = number
        if webhook_url:
            headers = {"X-OmniData-Secret": webhook_secret} if webhook_secret else {}
            body["webhook"] = {"enabled": True, "url": webhook_url, "events": ["MESSAGES_UPSERT"], "headers": headers}
        return _as_dict(await self._req("POST", "/instance/create", body))

    async def qrcode(self, name: str) -> dict[str, Any]:
        """Re-issues a QR code for an instance not yet connected (`base64`: a data: PNG; `code`: the raw pairing string)."""
        return _as_dict(await self._req("GET", f"/instance/connect/{name}"))

    async def connection_state(self, name: str) -> str:
        """One of 'open' (connected), 'connecting', 'close'."""
        d = _as_dict(await self._req("GET", f"/instance/connectionState/{name}"))
        return str(_as_dict(d.get("instance")).get("state", "close"))

    async def set_webhook(self, name: str, url: str, secret: str) -> None:
        """Confirmed 2026-09-22 against a real instance: the body must be wrapped under "webhook" — the flat shape
        some doc pages show ({"enabled": ..., "url": ...} at the top level) is rejected with a 400."""
        await self._req("POST", f"/webhook/set/{name}",
                        {"webhook": {"enabled": True, "url": url, "events": ["MESSAGES_UPSERT"], "headers": {"X-OmniData-Secret": secret}}})

    async def delete_instance(self, name: str) -> None:
        await self._req("DELETE", f"/instance/delete/{name}")

    async def fetch_instances(self) -> list[dict[str, Any]]:
        d = await self._req("GET", "/instance/fetchInstances")
        return _as_list(d)

    async def aclose(self) -> None:
        await self._http.aclose()


def verify_evolution_secret(secret: str, header_value: str | None) -> bool:
    """Evolution has no native request signature; the shared secret is a custom header WE set via `set_webhook`
    (`X-OmniData-Secret`) and check here, constant-time, the same pattern as the admin token in api/guard.py."""
    if not secret or not header_value:
        return False
    return hmac.compare_digest(secret, header_value)


def _numbered_text(body: str, options: list[tuple[str, str]]) -> str:
    """Degrades WhatsApp Business's native buttons/lists to plain numbered text: Baileys' buttonsMessage/listMessage
    have been unreliable on real devices since WhatsApp restricted native interactive UI to the official Business API
    (Evolution's own community steers users away from them). The reply id stays the leading token so a free-text
    numeric or exact-title reply keeps routing through the existing button/list handler (§ orchestrator _handle_reply_id
    already matches on id; the keyword router also matches plain text) — no behaviour change on the read side, only
    how the options are rendered on the wire."""
    lines = [body, ""]
    lines += [f"{i}. {title}" for i, (_id, title) in enumerate(options, 1)]
    lines.append("\nResponda com o número da opção.")
    return "\n".join(lines)


class EvolutionGateway:
    """MessagingGateway (D15) over Evolution API. `instance` is the name created with EvolutionAdminClient.create_instance."""

    def __init__(self, base_url: str, api_key: str, instance: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._instance = instance
        self._http = httpx.AsyncClient(transport=transport, timeout=20.0, headers={"apikey": api_key})

    async def _post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        try:
            r = await self._http.post(f"{self._base}{path}/{self._instance}", json=json)
        except httpx.TransportError as exc:
            raise GatewayError(f"evolution transport: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise GatewayError(f"evolution {r.status_code}: {r.text[:160]}")
        return dict(r.json()) if r.content else {}

    @staticmethod
    def _msg_id(d: dict[str, Any]) -> str:
        key = d.get("key") if isinstance(d.get("key"), dict) else d
        return str(key.get("id", "")) if isinstance(key, dict) else ""

    async def send_text(self, to: str, body: str) -> str:
        d = await self._post("/message/sendText", {"number": to.lstrip("+"), "text": body[:4096]})
        return self._msg_id(d)

    async def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> str:
        return await self.send_text(to, _numbered_text(body, buttons[:BUTTON_MAX]))

    async def send_list(self, to: str, body: str, button: str, rows: list[tuple[str, str, str]]) -> str:
        return await self.send_text(to, _numbered_text(body, [(i, t) for i, t, _d in rows]))

    async def send_template(self, to: str, name: str, params: list[str], quick_reply_payload: str | None = None) -> str:
        """Baileys has no official message-template system (that's a Cloud API feature); render as plain text.
        Every call site should prefer send_text with a string from strings_ptbr.py instead — kept only so
        EvolutionGateway satisfies MessagingGateway in full."""
        return await self.send_text(to, " ".join(params) or name)

    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        """OPEN-8: unverified against a real instance (no documented example). `media_id` here is the message id;
        Evolution's own convention (best current understanding) is to re-send the original message KEY, not a
        detached id, to /chat/getBase64FromMediaMessage. Kept isolated so it fails as a clean GatewayError — the
        orchestrator already turns that into "não consegui entender o áudio" (tested) rather than crashing."""
        d = await self._post("/chat/getBase64FromMediaMessage", {"message": {"key": {"id": media_id}}})
        b64, mime = d.get("base64"), d.get("mimetype") or "audio/ogg"
        if not isinstance(b64, str):
            raise GatewayError("evolution: no base64 media in response")
        import base64
        return base64.b64decode(b64), str(mime)

    async def send_document(self, to: str, filename: str, data: bytes, mime: str, caption: str = "") -> str:
        """Confirmed 2026-09-25 against the real instance: the body shape below (`mediatype`/`fileName`/`media`
        base64) works as documented — a real PDF sent this way arrived intact on WhatsApp."""
        import base64
        d = await self._post("/message/sendMedia", {"number": to.lstrip("+"), "mediatype": "document", "mimetype": mime,
                                                     "fileName": filename, "caption": caption, "media": base64.b64encode(data).decode()})
        return self._msg_id(d)

    async def send_presence(self, to: str, composing: bool, delay_ms: int = 1200) -> None:
        """Confirmed 2026-09-23 against the real instance: `delay` (ms) is required, undocumented — omitting it answers
        400 (`instance requires property "delay"`). Still best-effort (never raises): a bad presence call must never
        block the real reply from going out."""
        try:
            await self._post("/chat/sendPresence", {"number": to.lstrip("+"), "presence": "composing" if composing else "paused", "delay": delay_ms})
        except GatewayError:
            pass

    async def react(self, to: str, message_id: str, emoji: str) -> None:
        """Best-effort, same reasoning as send_presence. remoteJid is rebuilt as <number>@s.whatsapp.net — the inverse
        of webhook.py::normalize_phone — since Evolution's reaction endpoint needs the full key, not just the number."""
        try:
            await self._post("/message/sendReaction", {"key": {"remoteJid": f"{to.lstrip('+')}@s.whatsapp.net", "id": message_id, "fromMe": False},
                                                        "reaction": emoji})
        except GatewayError:
            pass

    async def aclose(self) -> None:
        await self._http.aclose()
