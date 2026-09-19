"""Anthropic adapter (Messages API, tool use). Default model per D11: claude-haiku-4-5-20251001."""
from __future__ import annotations

import time
from typing import Any

import httpx

from .base import LlmError, RouterResult, ToolCall, Usage

URL = "https://api.anthropic.com/v1/messages"


class AnthropicClient:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001",
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._model = model
        self._http = httpx.AsyncClient(transport=transport, timeout=30.0, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})

    async def _post(self, body: dict[str, Any]) -> tuple[dict[str, Any], Usage]:
        t0 = time.monotonic()
        try:
            r = await self._http.post(URL, json=body)
        except httpx.TransportError as exc:
            raise LlmError(f"transport: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise LlmError(f"anthropic {r.status_code}")
        d = r.json()
        u = d.get("usage", {})
        return d, Usage("anthropic", self._model, u.get("input_tokens", 0), u.get("output_tokens", 0),
                        int((time.monotonic() - t0) * 1000))

    async def route(self, system: str, user_text: str, tools: list[dict[str, Any]]) -> RouterResult:
        body = {"model": self._model, "max_tokens": 300, "system": system,
                "messages": [{"role": "user", "content": user_text}],
                "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]}
        d, usage = await self._post(body)
        for block in d.get("content", []):
            if block.get("type") == "tool_use":
                return RouterResult(ToolCall(block["name"], block.get("input", {})), None, usage)
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        return RouterResult(None, text or None, usage)

    async def narrate(self, system: str, payload_json: str) -> tuple[str, Usage]:
        d, usage = await self._post({"model": self._model, "max_tokens": 400, "system": system,
                                     "messages": [{"role": "user", "content": payload_json}]})
        return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text"), usage
