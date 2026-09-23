"""Provider fallback (FR-BOT-8): when the primary LLM errors, retry the same call against the next configured provider
before giving up to the caller's own degraded path. The orchestrator already treats LlmError as "no LLM available" for
this one call (falls back to the deterministic template/keyword route, ADR 0003) — this client just delays that error
until every provider in the chain has been tried, so ONE provider's outage never takes the assistant fully degraded."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from .base import LlmClient, LlmError, RouterResult, Usage

T = TypeVar("T")
OnFallback = Callable[[str, str, LlmError], None]


class FallbackLlmClient:
    """Tries `chain` in order for each call. `chain` is `[(client, label), ...]`; `label` is only for the audit log."""

    def __init__(self, chain: list[tuple[LlmClient, str]], on_fallback: OnFallback | None = None) -> None:
        if not chain:
            raise ValueError("chain must not be empty")
        self._chain = chain
        self._on_fallback = on_fallback  # optional (primary_label, next_label, error) -> None, for audit logging

    async def route(self, system: str, user_text: str, tools: list[dict[str, Any]]) -> RouterResult:
        return await self._try(lambda c: c.route(system, user_text, tools))

    async def narrate(self, system: str, payload_json: str) -> tuple[str, Usage]:
        return await self._try(lambda c: c.narrate(system, payload_json))

    async def _try(self, call: Callable[[LlmClient], Awaitable[T]]) -> T:
        last: LlmError | None = None
        for i, (client, label) in enumerate(self._chain):
            try:
                return await call(client)
            except LlmError as exc:
                last = exc
                nxt = self._chain[i + 1][1] if i + 1 < len(self._chain) else None
                if nxt and self._on_fallback:
                    self._on_fallback(label, nxt, exc)
        assert last is not None
        raise last
