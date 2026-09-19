"""Speech-to-text adapter (ADR 0004). Real ffmpeg decode of a real OGG/Opus file; HTTP is mocked."""
import shutil
import subprocess

import httpx
import pytest

from omnidata.llm.transcribe import OpenAITranscriber, TranscribeError, estimate_cost, to_wav, wav_seconds

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture(scope="module")
def ogg_opus(tmp_path_factory):
    """3 s of a 440 Hz tone as OGG/Opus 16 kbps mono, like a WhatsApp voice note."""
    p = tmp_path_factory.mktemp("aud") / "voice.ogg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-ac", "1",
                    "-ar", "16000", "-c:a", "libopus", "-b:a", "16k", str(p)], check=True)
    return p.read_bytes()


def multipart_fields(req: httpx.Request) -> dict[str, str]:
    body = req.content.decode("latin-1")
    out = {}
    for part in body.split("--")[1:]:
        if 'name="' in part and 'filename=' not in part:
            name = part.split('name="')[1].split('"')[0]
            out[name] = part.split("\r\n\r\n", 1)[1].rsplit("\r\n", 1)[0]
    return out


def transcriber(handler, **kw):
    return OpenAITranscriber("k", transport=httpx.MockTransport(handler), **kw)


async def test_ogg_opus_is_decoded_to_wav_with_exact_duration(ogg_opus):
    wav = await to_wav(ogg_opus)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE" and wav_seconds(wav) == pytest.approx(3.0, abs=0.15)


async def test_request_shape_for_gpt_transcribe_and_cost(ogg_opus):
    seen = {}

    def h(req):
        seen["url"], seen["auth"], seen["fields"], seen["body"] = str(req.url), req.headers["authorization"], multipart_fields(req), req.content
        return httpx.Response(200, json={"text": " Registra uma nota. ", "languages": ["pt"]})
    t = await transcriber(h).transcribe(ogg_opus, "audio/ogg")
    f = seen["fields"]
    assert seen["url"] == "https://api.openai.com/v1/audio/transcriptions" and seen["auth"] == "Bearer k"
    assert f["model"] == "gpt-transcribe" and f["languages[]"] == "pt" and "language" not in f and f["response_format"] == "json"
    assert "HubSpot" in f["prompt"] and b'filename="audio.wav"' in seen["body"]   # always a documented format (WAV), never raw OGG
    assert t.text == "Registra uma nota." and t.model == "gpt-transcribe"
    assert t.cost_usd == pytest.approx(0.0045 * t.seconds / 60, abs=1e-6) and t.seconds == pytest.approx(3.0, abs=0.15)


async def test_older_models_use_singular_language(ogg_opus):
    seen = {}
    def h(req):
        seen.update(multipart_fields(req)); return httpx.Response(200, json={"text": "ok"})
    await transcriber(h, model="gpt-4o-mini-transcribe").transcribe(ogg_opus)
    assert seen["language"] == "pt" and "languages[]" not in seen


async def test_language_hint_rejected_by_api_is_retried_without_it(ogg_opus):
    calls = []
    def h(req):
        f = multipart_fields(req); calls.append(f)
        return httpx.Response(400, text='{"error":{"message":"Unknown parameter: languages"}}') if len(calls) == 1 else httpx.Response(200, json={"text": "ok"})
    assert (await transcriber(h).transcribe(ogg_opus)).text == "ok"
    assert "languages[]" in calls[0] and "languages[]" not in calls[1] and "language" not in calls[1]


async def test_falls_back_to_mini_when_primary_model_is_not_available(ogg_opus):
    models = []
    def h(req):
        m = multipart_fields(req)["model"]; models.append(m)
        return httpx.Response(404, text='{"error":{"code":"model_not_found"}}') if m == "gpt-transcribe" else httpx.Response(200, json={"text": "ok"})
    t = await transcriber(h).transcribe(ogg_opus)
    assert models == ["gpt-transcribe", "gpt-4o-mini-transcribe"] and t.model == "gpt-4o-mini-transcribe"
    assert t.cost_usd == pytest.approx(0.003 * t.seconds / 60, abs=1e-6)   # cost follows the model actually used


async def test_too_long_is_refused_before_any_api_call(ogg_opus):
    called = []
    with pytest.raises(TranscribeError) as e:
        await transcriber(lambda r: called.append(1) or httpx.Response(200, json={"text": "x"}), max_seconds=1).transcribe(ogg_opus)
    assert e.value.code == "too_long" and called == []


async def test_too_big_and_undecodable_are_refused_without_api_call():
    called = []
    t = transcriber(lambda r: called.append(1) or httpx.Response(200, json={"text": "x"}), max_input_bytes=10)
    with pytest.raises(TranscribeError) as e1:
        await t.transcribe(b"x" * 11)
    with pytest.raises(TranscribeError) as e2:
        await transcriber(lambda r: called.append(1) or httpx.Response(200, json={"text": "x"})).transcribe(b"not audio at all")
    assert (e1.value.code, e2.value.code) == ("too_big", "decode") and called == []


async def test_server_errors_retry_then_raise_without_leaking_key(ogg_opus, monkeypatch):
    async def nosleep(_): ...
    monkeypatch.setattr("omnidata.llm.transcribe.asyncio.sleep", nosleep)
    n = []
    with pytest.raises(TranscribeError) as e:
        await transcriber(lambda r: n.append(1) or httpx.Response(503, text="down")).transcribe(ogg_opus)
    assert e.value.code == "api" and len(n) == 3 and "Bearer" not in str(e.value)


def test_price_table_matches_openai_pricing_page():  # checked 2026-09-19
    assert estimate_cost("gpt-transcribe", 60) == 0.0045 and estimate_cost("gpt-4o-mini-transcribe", 60) == 0.003
    assert estimate_cost("gpt-4o-transcribe", 60) == 0.006 == estimate_cost("whisper-1", 60)
