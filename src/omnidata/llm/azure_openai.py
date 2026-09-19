"""Azure OpenAI adapter (default provider, D11): chat completions with function calling + audio transcription."""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .base import LlmError, RouterResult, ToolCall, Usage

API_VERSION = "2024-10-21"


class AzureOpenAIClient:
    def __init__(self, endpoint: str, api_key: str, router_deployment: str, narrator_deployment: str,
                 transcribe_deployment: str = "", transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base = endpoint.rstrip("/")
        self._router, self._narrator, self._transcribe = router_deployment, narrator_deployment, transcribe_deployment
        self._http = httpx.AsyncClient(transport=transport, timeout=30.0, headers={"api-key": api_key})

    async def _chat(self, deployment: str, body: dict[str, Any]) -> tuple[dict[str, Any], Usage]:
        url = f"{self._base}/openai/deployments/{deployment}/chat/completions?api-version={API_VERSION}"
        t0 = time.monotonic()
        try:
            r = await self._http.post(url, json=body)
        except httpx.TransportError as exc:
            raise LlmError(f"transport: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise LlmError(f"azure_openai {r.status_code}")
        d = r.json()
        u = d.get("usage", {})
        return d, Usage("azure_openai", deployment, u.get("prompt_tokens", 0), u.get("completion_tokens", 0),
                        int((time.monotonic() - t0) * 1000))

    async def route(self, system: str, user_text: str, tools: list[dict[str, Any]]) -> RouterResult:
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user_text}],
                "tools": [{"type": "function", "function": t} for t in tools], "tool_choice": "auto", "temperature": 0}
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
            {"role": "system", "content": system}, {"role": "user", "content": payload_json}], "temperature": 0.2})
        return d["choices"][0]["message"].get("content") or "", usage

    async def transcribe(self, audio: bytes, mime: str) -> str:
        if not self._transcribe:
            raise LlmError("AZURE_OPENAI_DEPLOYMENT_TRANSCRIBE is not set")
        url = f"{self._base}/openai/deployments/{self._transcribe}/audio/transcriptions?api-version={API_VERSION}"
        r = await self._http.post(url, files={"file": ("audio.ogg", audio, mime)}, data={"language": "pt"})
        if r.status_code >= 400:
            raise LlmError(f"azure transcribe {r.status_code}")
        return str(r.json().get("text", ""))
