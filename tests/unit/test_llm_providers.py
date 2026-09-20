"""LLM provider selection (no network): deepseek reuses the OpenAI-compatible client with its own key, URL and telemetry label."""
import asyncio

import httpx

from omnidata.config import Settings
from omnidata.jobs.worker import build_llm
from omnidata.llm.openai_chat import OpenAIChatClient


def test_deepseek_needs_key_and_both_models_and_never_uses_the_openai_key():
    base = dict(llm_provider="deepseek", anthropic_api_key="", openai_api_key="sk-openai", deepseek_api_key="", deepseek_model_router="", deepseek_model_narrator="")
    assert build_llm(Settings(**base)) is None                                                    # nothing set: degraded mode
    assert build_llm(Settings(**{**base, "deepseek_api_key": "k", "deepseek_model_router": "m"})) is None    # a model is missing
    llm = build_llm(Settings(**{**base, "deepseek_api_key": "k", "deepseek_model_router": "m1", "deepseek_model_narrator": "m2"}))
    assert isinstance(llm, OpenAIChatClient) and llm._base == "https://api.deepseek.com" and llm._provider == "deepseek"


def test_request_goes_to_the_deepseek_url_with_its_key_and_is_labelled_deepseek():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"] = str(req.url), req.headers["authorization"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "oi"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}})

    c = OpenAIChatClient("k-deep", "flash", "flash", "https://api.deepseek.com", httpx.MockTransport(handler), provider="deepseek")
    text, usage = asyncio.run(c.narrate("s", "{}"))
    assert seen["url"] == "https://api.deepseek.com/chat/completions" and seen["auth"] == "Bearer k-deep"
    assert text == "oi" and usage.provider == "deepseek" and usage.model == "flash"
