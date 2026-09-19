"""LlmClient interface (D11). Two edges only: tool selection and narration (D7)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class Usage:
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


@dataclass
class RouterResult:
    tool: ToolCall | None
    text: str | None
    usage: Usage = field(default_factory=lambda: Usage("none", "none"))


class LlmError(RuntimeError):
    pass


class LlmClient(Protocol):
    async def route(self, system: str, user_text: str, tools: list[dict[str, Any]]) -> RouterResult: ...
    async def narrate(self, system: str, payload_json: str) -> tuple[str, Usage]: ...
    async def transcribe(self, audio: bytes, mime: str) -> str: ...
