"""In-memory fakes for the outside world: WhatsApp gateway, HubSpot writer, LLM."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from omnidata.crm.hubspot.client import HubSpotError
from omnidata.llm.base import LlmError, RouterResult, ToolCall, Usage
from omnidata.llm.transcribe import TranscribeError, Transcript


class FakeGateway:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.reacted: list[tuple[str, str, str]] = []
        self.presence: list[tuple[str, bool]] = []

    async def send_presence(self, to: str, composing: bool, delay_ms: int = 1200) -> None:
        self.presence.append((to, composing))

    async def react(self, to: str, message_id: str, emoji: str) -> None:
        self.reacted.append((to, message_id, emoji))

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
    def __init__(self, tool: ToolCall | None = None, narration: str | None = None, down: bool = False, router_text: str | None = None) -> None:
        self.tool, self.narration, self.down, self.router_text = tool, narration, down, router_text
        self.router_inputs: list[str] = []
        self.narrator_systems: list[str] = []

    async def route(self, system: str, user_text: str, tools: list[dict[str, Any]]) -> RouterResult:
        self.router_inputs.append(user_text)
        if self.down:
            raise LlmError("down")
        return RouterResult(self.tool, self.router_text, Usage("fake", "fake", 10, 5))

    async def narrate(self, system: str, payload_json: str) -> tuple[str, Usage]:
        self.narrator_systems.append(system)
        if self.down:
            raise LlmError("down")
        return self.narration or "", Usage("fake", "fake", 10, 5)


class FakeTranscriber:
    def __init__(self, text: str = "como estou na meta", error: str | None = None, seconds: float = 12.0, model: str = "gpt-transcribe") -> None:
        self.text, self.error, self.seconds, self.model, self.calls = text, error, seconds, model, 0

    async def transcribe(self, audio: bytes, mime: str) -> Transcript:
        self.calls += 1
        if self.error:
            raise TranscribeError(self.error)
        return Transcript(self.text, self.model, self.seconds, round(0.0045 * self.seconds / 60, 6), 300)


class FakeEmbeddings:
    """Deterministic, no network: same text -> same vector, so tests can assert nearest-match ordering."""
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float((hash(t) >> (8 * i)) % 997) for i in range(4)] for t in texts]


class FakeVectorStore:
    """In-memory stand-in for Chroma (ADR 0009). query() ignores `where` on purpose: the point of the permission tests is
    that bot/repo.py::meeting_transcripts_by_ids re-checks ownership in Postgres regardless of what the index returns."""
    def __init__(self) -> None:
        self.rows: dict[str, tuple[list[float], dict[str, Any]]] = {}

    def upsert(self, ids: list[str], embeddings: list[list[float]], metadatas: list[dict[str, Any]]) -> None:
        for i, e, m in zip(ids, embeddings, metadatas, strict=True):
            self.rows[i] = (e, m)

    def query(self, embedding: list[float], limit: int, where: dict[str, Any] | None = None) -> list[tuple[str, float]]:
        def dist(v: list[float]) -> float:
            return sum((a - b) ** 2 for a, b in zip(embedding, v, strict=True))
        ranked = sorted(self.rows.items(), key=lambda kv: dist(kv[1][0]))
        return [(i, dist(v)) for i, (v, _) in ranked[:limit]]
