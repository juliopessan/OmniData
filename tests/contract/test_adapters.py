"""Request/response shapes of the external APIs, against recorded-style mock transports (no live calls)."""
import json

import httpx

from omnidata.bot.gateway import WhatsAppCloudGateway
from omnidata.crm.hubspot.client import HubSpotClient
from omnidata.crm.hubspot.writeback import NOTE_TO_DEAL, HubSpotWriter
from omnidata.llm.anthropic import AnthropicClient
from omnidata.llm.azure_openai import AzureOpenAIClient


async def test_whatsapp_send_shapes():
    seen = []

    def h(req):
        seen.append((str(req.url), json.loads(req.content), req.headers["authorization"]))
        return httpx.Response(200, json={"messages": [{"id": "wamid.ok"}]})
    gw = WhatsAppCloudGateway("PNID", "TOKEN", transport=httpx.MockTransport(h))
    assert await gw.send_text("+5511999", "oi") == "wamid.ok"
    await gw.send_buttons("+5511999", "ok?", [("act:confirm:1", "Confirmar")])
    await gw.send_template("+5511999", "morning_brief_v1", ["Ana", "3"], "act:open:brief")
    url, body, auth = seen[0]
    assert url.endswith("/PNID/messages") and auth == "Bearer TOKEN" and body["to"] == "5511999" and body["messaging_product"] == "whatsapp"
    assert seen[1][1]["interactive"]["action"]["buttons"][0]["reply"]["id"] == "act:confirm:1"
    tpl = seen[2][1]["template"]
    assert tpl["language"]["code"] == "pt_BR" and tpl["components"][1]["sub_type"] == "quick_reply"


async def test_whatsapp_error_raises_without_leaking_token():
    import pytest

    from omnidata.bot.gateway import GatewayError
    gw = WhatsAppCloudGateway("P", "SECRET", transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad")))
    with pytest.raises(GatewayError) as e:
        await gw.send_text("+55", "x")
    assert "SECRET" not in str(e.value)


async def test_azure_openai_route_parses_function_call_and_usage():
    def h(req):
        assert "/deployments/router/chat/completions" in str(req.url) and req.headers["api-key"] == "k"
        body = json.loads(req.content)
        assert body["tools"][0]["type"] == "function" and body["temperature"] == 0
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"function": {"name": "get_kpis", "arguments": '{"period":"last_month"}'}}]}}],
                                         "usage": {"prompt_tokens": 12, "completion_tokens": 3}})
    c = AzureOpenAIClient("https://x.openai.azure.com", "k", "router", "narr", transport=httpx.MockTransport(h))
    res = await c.route("sys", "meus números", [{"name": "get_kpis", "description": "d", "parameters": {"type": "object"}}])
    assert res.tool and res.tool.name == "get_kpis" and res.tool.arguments == {"period": "last_month"} and res.usage.input_tokens == 12


async def test_anthropic_route_parses_tool_use():
    def h(req):
        assert req.headers["x-api-key"] == "k" and json.loads(req.content)["model"] == "claude-haiku-4-5-20251001"
        return httpx.Response(200, json={"content": [{"type": "tool_use", "name": "get_quota_status", "input": {}}], "usage": {"input_tokens": 5, "output_tokens": 2}})
    res = await AnthropicClient("k", transport=httpx.MockTransport(h)).route("s", "meta", [{"name": "get_quota_status", "description": "d", "parameters": {"type": "object"}}])
    assert res.tool and res.tool.name == "get_quota_status"


async def test_llm_http_error_becomes_llm_error():
    import pytest

    from omnidata.llm.base import LlmError
    with pytest.raises(LlmError):
        await AnthropicClient("k", transport=httpx.MockTransport(lambda r: httpx.Response(529))).narrate("s", "{}")


async def test_hubspot_writeback_payloads():
    seen = []

    def h(req):
        seen.append((req.method, req.url.path, json.loads(req.content) if req.content else None))
        return httpx.Response(200, json={"id": "77", "properties": {"amount": "1"}})
    async def ns(_): ...
    w = HubSpotWriter(HubSpotClient("t", transport=httpx.MockTransport(h), sleep=ns))
    assert await w.create_note("D1", "texto", "9000") == "77"
    m, path, body = seen[0]
    assert (m, path) == ("POST", "/crm/v3/objects/notes") and body["associations"][0]["types"][0]["associationTypeId"] == NOTE_TO_DEAL
    await w.update_deal("D1", {"amount": "5"})
    assert seen[1][:2] == ("PATCH", "/crm/v3/objects/deals/D1")


async def test_archive_treats_404_as_already_done():
    async def ns(_): ...
    w = HubSpotWriter(HubSpotClient("t", transport=httpx.MockTransport(lambda r: httpx.Response(404, text="gone")), sleep=ns))
    await w.archive("notes", "1")  # must not raise
