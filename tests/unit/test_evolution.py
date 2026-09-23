"""EvolutionAdminClient (instance lifecycle, ADR 0008) and the webhook payload parser, against the documented request/
response shapes (https://docs.evolutionfoundation.com.br, fetched 2026-09-22). No live Evolution instance involved."""
import asyncio
import json

import httpx

from omnidata.bot.evolution import EvolutionAdminClient
from omnidata.bot.webhook import extract_events, message_kind, normalize_phone


def test_create_instance_sends_baileys_integration_and_the_webhook_secret_header():
    seen = {}

    def h(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["apikey"], seen["body"] = str(req.url), req.headers["apikey"], json.loads(req.content)
        return httpx.Response(201, json={"instance": {"instanceName": "omnidata"}, "qrcode": {"base64": "data:image/png;base64,QQ=="}})

    c = EvolutionAdminClient("https://evo.example.com", "GLOBAL", httpx.MockTransport(h))
    res = asyncio.run(c.create_instance("omnidata", number="+5511999999999", webhook_url="https://api.example.com/webhooks/evolution",
                                        webhook_secret="s3cret"))
    assert seen["url"] == "https://evo.example.com/instance/create" and seen["apikey"] == "GLOBAL"
    assert seen["body"]["instanceName"] == "omnidata" and seen["body"]["integration"] == "WHATSAPP-BAILEYS" and seen["body"]["number"] == "+5511999999999"
    assert seen["body"]["webhook"] == {"enabled": True, "url": "https://api.example.com/webhooks/evolution",
                                       "events": ["MESSAGES_UPSERT"], "headers": {"X-OmniData-Secret": "s3cret"}}
    assert res["qrcode"]["base64"] == "data:image/png;base64,QQ=="


def test_create_instance_without_a_webhook_url_sends_no_webhook_field():
    seen = {}

    def h2(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(201, json={})
    c = EvolutionAdminClient("https://evo.example.com", "GLOBAL", httpx.MockTransport(h2))
    asyncio.run(c.create_instance("omnidata"))
    assert "webhook" not in seen["body"] and "number" not in seen["body"]


def test_qrcode_and_connection_state_read_the_documented_response_shape():
    c1 = EvolutionAdminClient("https://evo.example.com", "K",
                              httpx.MockTransport(lambda r: httpx.Response(200, json={"base64": "data:image/png;base64,Zg==", "count": 1})))
    assert asyncio.run(c1.qrcode("omnidata"))["base64"].startswith("data:image/png")
    c2 = EvolutionAdminClient("https://evo.example.com", "K",
                              httpx.MockTransport(lambda r: httpx.Response(200, json={"instance": {"instanceName": "omnidata", "state": "open"}})))
    assert asyncio.run(c2.connection_state("omnidata")) == "open"


def test_fetch_instances_accepts_either_a_bare_array_or_a_wrapped_object():
    bare = EvolutionAdminClient("https://e", "K", httpx.MockTransport(lambda r: httpx.Response(200, json=[{"name": "a"}])))
    assert asyncio.run(bare.fetch_instances()) == [{"name": "a"}]
    wrapped = EvolutionAdminClient("https://e", "K", httpx.MockTransport(lambda r: httpx.Response(200, json={"instances": [{"name": "b"}]})))
    assert asyncio.run(wrapped.fetch_instances()) == [{"name": "b"}]


def test_delete_instance_and_error_propagation():
    import pytest

    from omnidata.bot.gateway import GatewayError
    ok = EvolutionAdminClient("https://e", "K", httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    asyncio.run(ok.delete_instance("omnidata"))  # no exception
    bad = EvolutionAdminClient("https://e", "K", httpx.MockTransport(lambda r: httpx.Response(404, text="not found")))
    with pytest.raises(GatewayError):
        asyncio.run(bad.delete_instance("ghost"))


# ---------------- webhook payload parsing ----------------
def test_normalize_phone_strips_the_whatsapp_jid_suffix():
    assert normalize_phone("5511999999999@s.whatsapp.net") == "+5511999999999"
    assert normalize_phone("+5511999999999@s.whatsapp.net") == "+5511999999999"


def test_extract_events_only_matches_messages_upsert_and_handles_single_or_batched_data():
    up = {"event": "messages.upsert", "data": {"key": {"id": "1"}}}
    assert extract_events(up) == [{"key": {"id": "1"}}]
    batched = {"event": "MESSAGES_UPSERT", "data": [{"key": {"id": "1"}}, {"key": {"id": "2"}}]}
    assert len(extract_events(batched)) == 2
    assert extract_events({"event": "CONNECTION_UPDATE", "data": {}}) == []


def test_message_kind_covers_text_audio_and_interactive_replies():
    assert message_kind({"message": {"conversation": "oi"}}) == ("text", {"text": "oi"})
    assert message_kind({"message": {"extendedTextMessage": {"text": "oi de novo"}}}) == ("text", {"text": "oi de novo"})
    kind, body = message_kind({"key": {"id": "M1"}, "message": {"audioMessage": {"mimetype": "audio/ogg; codecs=opus"}}})
    assert kind == "audio" and body == {"media_id": "M1", "mime": "audio/ogg; codecs=opus"}
    kind, body = message_kind({"message": {"buttonsResponseMessage": {"selectedButtonId": "menu:kpis", "selectedDisplayText": "Meus números"}}})
    assert (kind, body) == ("interactive", {"reply_id": "menu:kpis", "title": "Meus números"})
    kind, body = message_kind({"message": {"listResponseMessage": {"singleSelectReply": {"selectedRowId": "menu:quota"}}}})
    assert (kind, body) == ("interactive", {"reply_id": "menu:quota", "title": ""})
    assert message_kind({"message": {"reactionMessage": {}}}) is None
