"""In-memory fakes for the outside world: WhatsApp gateway, HubSpot writer, LLM."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from omnidata.crm.hubspot.client import HubSpotError
from omnidata.llm.base import LlmError, RouterResult, ToolCall, Usage


class FakeGateway:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, to: str, body: str) -> str:
        self.sent.append({"to": to, "type": "text", "body": body}); return "wamid.1"

    async def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> str:
        self.sent.append({"to": to, "type": "buttons", "body": body, "buttons": buttons}); return "wamid.2"

    async def send_list(self, to: str, body: str, button: str, rows: list[tuple[str, str, str]]) -> str:
        self.sent.append({"to": to, "type": "list", "body": body, "rows": rows}); return "wamid.3"

    async def send_template(self, to: str, name: str, params: list[str], quick_reply_payload: str | None = None) -> str:
        self.sent.append({"to": to, "type": "template", "name": name, "params": params, "payload": quick_reply_payload}); return "wamid.4"

    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        return b"audio", "audio/ogg"

    @property
    def last(self) -> dict[str, Any]:
        return self.sent[-1]


class FakeWriter:
    """Mimics HubSpotWriter; `deal_props` is the 'CRM' so tests can simulate a colleague's later edit."""
    def __init__(self) -> None:
        self.fail = False
        self.n = 0
        self.deal_props: dict[str, dict[str, Any]] = {}
        self.created: list[tuple[str, str]] = []
        self.archived: list[tuple[str, str]] = []
        self.updates: list[tuple[str, dict[str, Any]]] = []

    def _check(self) -> None:
        if self.fail:
            raise HubSpotError(503, "down")

    async def create_note(self, deal_id: str, text: str, owner_id: str | None = None) -> str:
        self._check(); self.n += 1; self.created.append(("notes", str(self.n))); return str(self.n)

    async def create_task(self, deal_id: str, title: str, due: datetime, owner_id: str | None = None) -> str:
        self._check(); self.n += 1; self.created.append(("tasks", str(self.n))); return str(self.n)

    async def get_deal_props(self, deal_id: str, props: list[str]) -> dict[str, Any]:
        self._check(); return {p: self.deal_props.get(deal_id, {}).get(p) for p in props}

    async def update_deal(self, deal_id: str, props: dict[str, Any]) -> dict[str, Any]:
        self._check(); self.deal_props.setdefault(deal_id, {}).update(props); self.updates.append((deal_id, props)); return {}

    async def update_object(self, object_type: str, object_id: str, props: dict[str, Any]) -> dict[str, Any]:
        self._check(); return {}

    async def archive(self, object_type: str, object_id: str) -> None:
        self._check(); self.archived.append((object_type, object_id))


class FakeLlm:
    def __init__(self, tool: ToolCall | None = None, narration: str | None = None, down: bool = False) -> None:
        self.tool, self.narration, self.down = tool, narration, down
        self.router_inputs: list[str] = []

    async def route(self, system: str, user_text: str, tools: list[dict[str, Any]]) -> RouterResult:
        self.router_inputs.append(user_text)
        if self.down:
            raise LlmError("down")
        return RouterResult(self.tool, None, Usage("fake", "fake", 10, 5))

    async def narrate(self, system: str, payload_json: str) -> tuple[str, Usage]:
        if self.down:
            raise LlmError("down")
        return self.narration or "", Usage("fake", "fake", 10, 5)

    async def transcribe(self, audio: bytes, mime: str) -> str:
        return "como estou na meta"
