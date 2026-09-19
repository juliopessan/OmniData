"""Speech-to-text for WhatsApp voice notes (FR-BOT-5). Separate from the chat LLM so the two can change independently.

Decisions (ADR 0004):
- Default model `gpt-transcribe` ($0.0045/min, the model OpenAI recommends for recorded speech); fallback
  `gpt-4o-mini-transcribe` ($0.003/min) when the primary is unavailable to the account.
- WhatsApp voice notes are OGG/Opus, which OpenAI's docs do NOT list as supported. We always decode to 16 kHz mono WAV
  (documented format) with ffmpeg. The duration is then exact, so cost and length limits are enforced BEFORE any API call.
- `gpt-transcribe` takes `languages[]`, older models take `language`; if the API rejects the hint we retry without it.
Not verified against the live API yet (the key supplied for testing was invalidated): run scripts/bench_transcribe.py."""
from __future__ import annotations

import asyncio
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

DEFAULT_BASE_URL = "https://api.openai.com/v1"
# USD per audio minute (OpenAI pricing page, checked 2026-09-19)
PRICE_PER_MIN = {"gpt-transcribe": 0.0045, "gpt-4o-transcribe": 0.006, "gpt-4o-mini-transcribe": 0.003, "whisper-1": 0.006}
LANGUAGES_PLURAL = {"gpt-transcribe"}  # models that use `languages[]` instead of `language`
# Vocabulary hint only. NEVER put names, phones, e-mails or deal data here.
VOCAB_PROMPT = ("Conversa de vendas em português do Brasil. Vocabulário: HubSpot, negócio, etapa, qualificação, proposta, "
                "negociação, fechamento, meta, pipeline, follow-up, nota, tarefa, cobertura, win rate.")
WAV_HEADER = 44
SAMPLE_RATE = 16_000


class TranscribeError(RuntimeError):
    """code: too_big | too_long | decode | api"""
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class Transcript:
    text: str
    model: str
    seconds: float
    cost_usd: float
    latency_ms: int


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, mime: str) -> Transcript: ...


def wav_seconds(wav: bytes) -> float:
    return max(0.0, (len(wav) - WAV_HEADER) / (SAMPLE_RATE * 2))  # 16-bit mono


def estimate_cost(model: str, seconds: float) -> float:
    return round(PRICE_PER_MIN.get(model, 0.006) * seconds / 60, 6)


async def to_wav(audio: bytes, ffmpeg: str = "ffmpeg", timeout: float = 20.0) -> bytes:
    """Decode any container/codec (OGG/Opus, AAC, AMR...) to 16 kHz mono PCM WAV. Temp files are removed right away."""
    with tempfile.TemporaryDirectory(prefix="omni-audio-") as d:
        src, dst = Path(d, "in.bin"), Path(d, "out.wav")
        src.write_bytes(audio)
        try:
            proc = await asyncio.create_subprocess_exec(
                ffmpeg, "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
                "-c:a", "pcm_s16le", str(dst), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(proc.wait(), timeout)
        except (FileNotFoundError, TimeoutError) as exc:
            raise TranscribeError("decode", f"ffmpeg unavailable or timed out: {type(exc).__name__}") from exc
        if proc.returncode != 0 or not dst.exists():
            raise TranscribeError("decode", "undecodable audio")
        return dst.read_bytes()


class _ModelUnavailable(Exception):
    pass


class OpenAITranscriber:
    def __init__(self, api_key: str, model: str = "gpt-transcribe", fallback_model: str = "gpt-4o-mini-transcribe",
                 base_url: str = DEFAULT_BASE_URL, max_seconds: int = 180, max_input_bytes: int = 5_000_000,
                 transport: httpx.AsyncBaseTransport | None = None, ffmpeg: str = "ffmpeg") -> None:
        self._models = [m for i, m in enumerate([model, fallback_model]) if m and m not in ([model, fallback_model][:i])]
        self._base, self._max_s, self._max_b, self._ffmpeg = base_url.rstrip("/"), max_seconds, max_input_bytes, ffmpeg
        self._http = httpx.AsyncClient(transport=transport, timeout=60.0, headers={"Authorization": f"Bearer {api_key}"})

    async def transcribe(self, audio: bytes, mime: str = "audio/ogg") -> Transcript:
        if len(audio) > self._max_b:
            raise TranscribeError("too_big")
        wav = await to_wav(audio, self._ffmpeg)
        secs = wav_seconds(wav)
        if secs > self._max_s:
            raise TranscribeError("too_long")
        t0 = time.monotonic()
        for model in self._models:
            try:
                text = await self._call(model, wav)
            except _ModelUnavailable:
                continue
            return Transcript(text, model, round(secs, 2), estimate_cost(model, secs), int((time.monotonic() - t0) * 1000))
        raise TranscribeError("api", "no transcription model available")

    async def _call(self, model: str, wav: bytes) -> str:
        use_lang = True
        for attempt in range(3):
            data = {"model": model, "response_format": "json", "prompt": VOCAB_PROMPT}
            if use_lang:
                data["languages[]" if model in LANGUAGES_PLURAL else "language"] = "pt"
            try:
                r = await self._http.post(f"{self._base}/audio/transcriptions", data=data,
                                          files={"file": ("audio.wav", wav, "audio/wav")})
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise TranscribeError("api", f"transport: {type(exc).__name__}") from exc
                await asyncio.sleep(1 + attempt)
                continue
            if r.status_code == 200:
                return str(r.json().get("text", "")).strip()
            if r.status_code == 400 and use_lang and "language" in r.text.lower():
                use_lang = False  # the model rejected the language hint: let it auto-detect
                continue
            if r.status_code in (403, 404) or "model_not_found" in r.text:
                raise _ModelUnavailable(model)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == 2:
                    raise TranscribeError("api", f"http {r.status_code}")
                await asyncio.sleep(1 + attempt)
                continue
            raise TranscribeError("api", f"http {r.status_code}")
        raise TranscribeError("api", "retries exhausted")
