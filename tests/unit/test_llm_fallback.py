"""OpenRouter as a fallback provider (FR-BOT-8): tried only after the primary errors, never before, and only on LlmError —
never for a wrong-answer plan (that's Orion's own validation, not a transport failure)."""
import asyncio

import httpx
import pytest

from omnidata.config import Settings
from omnidata.jobs.worker import build_llm
from omnidata.llm.base import LlmError, RouterResult, ToolCall, Usage
from omnidata.llm.fallback import FallbackLlmClient
from omnidata.llm.openai_chat import OpenAIChatClient

BASE = dict(llm_provider="deepseek", anthropic_api_key="", openai_api_key="", deepseek_api_key="", deepseek_model_router="",
            deepseek_model_narrator="", openrouter_api_key="", openrouter_model_router="", openrouter_model_narrator="")
DEEPSEEK = dict(deepseek_api_key="k-deep", deepseek_model_router="dr", deepseek_model_narrator="dn")
OPENROUTER = dict(openrouter_api_key="k-or", openrouter_model_router="or/model", openrouter_model_narrator="or/model")


def test_openrouter_alone_needs_both_models_and_is_used_only_when_configured():
    assert build_llm(Settings(**BASE)) is None                                                          # nothing configured: degraded mode
    assert build_llm(Settings(**{**BASE, "openrouter_api_key": "k", "openrouter_model_router": "m"})) is None  # missing narrator model
    llm = build_llm(Settings(**{**BASE, **OPENROUTER}))                                                  # no primary, only OpenRouter
    assert isinstance(llm, OpenAIChatClient) and llm._provider == "openrouter" and llm._base == "https://openrouter.ai/api/v1"


def test_a_working_primary_alone_is_returned_unwrapped_openrouter_is_never_touched():
    llm = build_llm(Settings(**{**BASE, **DEEPSEEK}))
    assert isinstance(llm, OpenAIChatClient) and llm._provider == "deepseek"       # not wrapped: no chain overhead when there's nothing to fall back to


def test_both_configured_builds_a_fallback_chain_with_deepseek_first():
    llm = build_llm(Settings(**{**BASE, **DEEPSEEK, **OPENROUTER}))
    assert isinstance(llm, FallbackLlmClient)
    assert [label for _, label in llm._chain] == ["deepseek", "openrouter"]


class Boom:
    """A client that always raises, so the chain must move past it."""
    async def route(self, system, user_text, tools):
        raise LlmError("boom")

    async def narrate(self, system, payload_json):
        raise LlmError("boom")


class Ok:
    def __init__(self, provider: str) -> None:
        self.provider = provider

    async def route(self, system, user_text, tools):
        return RouterResult(ToolCall("get_kpis", {}), None, Usage(self.provider, "m"))

    async def narrate(self, system, payload_json):
        return f"ok from {self.provider}", Usage(self.provider, "m")


def test_route_and_narrate_fall_through_to_the_next_provider_on_llmerror():
    fb = FallbackLlmClient([(Boom(), "deepseek"), (Ok("openrouter"), "openrouter")])
    res = asyncio.run(fb.route("s", "u", []))
    assert res.tool and res.usage.provider == "openrouter"
    text, usage = asyncio.run(fb.narrate("s", "{}"))
    assert text == "ok from openrouter" and usage.provider == "openrouter"


def test_the_primary_answering_never_touches_the_fallback():
    class Tripwire(Boom):
        async def route(self, system, user_text, tools):
            raise AssertionError("fallback must not be called when the primary succeeds")

    fb = FallbackLlmClient([(Ok("deepseek"), "deepseek"), (Tripwire(), "openrouter")])
    res = asyncio.run(fb.route("s", "u", []))
    assert res.usage.provider == "deepseek"


def test_every_provider_failing_raises_the_last_error_not_a_silent_none():
    fb = FallbackLlmClient([(Boom(), "deepseek"), (Boom(), "openrouter")])
    with pytest.raises(LlmError):
        asyncio.run(fb.route("s", "u", []))


def test_on_fallback_callback_fires_once_per_switch_naming_who_failed_and_who_is_next():
    calls = []
    fb = FallbackLlmClient([(Boom(), "deepseek"), (Ok("openrouter"), "openrouter")], on_fallback=lambda a, b, e: calls.append((a, b)))
    asyncio.run(fb.route("s", "u", []))
    assert calls == [("deepseek", "openrouter")]


def test_a_chain_cannot_be_built_empty():
    with pytest.raises(ValueError):
        FallbackLlmClient([])


def test_openrouter_request_carries_its_key_url_and_optional_referer_headers():
    """Same MockTransport pattern as the deepseek client test: pass the transport at construction, never mutate a live client."""
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["referer"] = req.headers.get("http-referer")
        seen["title"] = req.headers.get("x-title")
        return httpx.Response(200, json={"choices": [{"message": {"content": "oi"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    c = OpenAIChatClient("k-or", "or/model", "or/model", "https://openrouter.ai/api/v1", httpx.MockTransport(handler),
                         provider="openrouter", extra_headers={"HTTP-Referer": "https://omnidata-web-eta.vercel.app", "X-Title": "OmniData"})
    asyncio.run(c.narrate("s", "{}"))
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions" and seen["auth"] == "Bearer k-or"
    assert seen["referer"] == "https://omnidata-web-eta.vercel.app" and seen["title"] == "OmniData"


def test_openrouter_headers_are_omitted_when_not_configured():
    """build_llm builds the real client (no transport override) but never sends: this only checks the headers it would send."""
    llm = build_llm(Settings(**{**BASE, **OPENROUTER}))
    assert isinstance(llm, OpenAIChatClient)
    assert "http-referer" not in {k.lower() for k in llm._http.headers} and "x-title" not in {k.lower() for k in llm._http.headers}
