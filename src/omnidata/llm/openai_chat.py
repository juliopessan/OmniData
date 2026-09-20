"""OpenAI chat adapter (function calling). `base_url` is configurable so any OpenAI-compatible endpoint can be used
(e.g. an AI gateway). Models come from env: there is deliberately no hard-coded default model name."""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .base import LlmError, RouterResult, ToolCall, Usage

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIChatClient:
    def __init__(self, api_key: str, router_model: str, narrator_model: str, base_url: str = DEFAULT_BASE_URL,
                 transport: httpx.AsyncBaseTransport | None = None, provider: str = "openai") -> None:
        self._provider = provider  # label in telemetry: any OpenAI-compatible endpoint (e.g. deepseek)
        self._base = base_url.rstrip("/")
        self._router, self._narrator = router_model, narrator_model
        self._http = httpx.AsyncClient(transport=transport, timeout=30.0, headers={"Authorization": f"Bearer {api_key}"})

    async def _chat(self, model: str, body: dict[str, Any]) -> tuple[dict[str, Any], Usage]:
        t0 = time.monotonic()
        try:
            r = await self._http.post(f"{self._base}/chat/completions", json={"model": model, **body})
        except httpx.TransportError as exc:
            raise LlmError(f"transport: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise LlmError(f"{self._provider} {r.status_code}")
        d = r.json()
        u = d.get("usage", {})
        return d, Usage(self._provider, model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), int((time.monotonic() - t0) * 1000))

    async def route(self, system: str, user_text: str, tools: list[dict[str, Any]]) -> RouterResult:
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user_text}],
                "tools": [{"type": "function", "function": t} for t in tools], "tool_choice": "auto"}
        d, usage = await self._chat(self._router, body)
        msg = d["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if calls:
            fn = calls[0]["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                raise LlmError("invalid tool arguments") from exc
            return RouterResult(ToolCall(fn["name"], args), None, usage)
        return RouterResult(None, msg.get("content"), usage)

    async def narrate(self, system: str, payload_json: str) -> tuple[str, Usage]:
        d, usage = await self._chat(self._narrator, {"messages": [
            {"role": "system", "content": system}, {"role": "user", "content": payload_json}]})
        return d["choices"][0]["message"].get("content") or "", usage
