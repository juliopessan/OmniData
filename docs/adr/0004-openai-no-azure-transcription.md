# ADR 0004: no Azure; OpenAI direct for chat (optional) and speech-to-text (amends D11)
- Status: accepted · Date: 2026-09-19 · Decision-log row: **D11 amended** (was: Azure OpenAI default, Anthropic second)

## Context
The team already runs on Vercel and does not want Azure in the project. Voice notes (WhatsApp OGG/Opus) need transcription (FR-BOT-5).

## Decision
1. **Azure removed** (adapter, settings, docs). Chat providers: `anthropic` (default, `claude-haiku-4-5-20251001`) or `openai`
   (`OPENAI_BASE_URL` configurable, so an OpenAI-compatible gateway can be used; model names come from env, no baked-in default).
2. **Transcription is its own interface** (`llm/transcribe.py: Transcriber`), independent of the chat provider. Implementation: OpenAI `/audio/transcriptions`.
3. **Model: `gpt-transcribe` by default, `gpt-4o-mini-transcribe` as fallback.** Prices (OpenAI pricing page, 2026-09-19):

   | Model | $/min | Verdict |
   |---|---|---|
   | gpt-4o-mini-transcribe | 0.003 | cheapest; keep as fallback / cost lever |
   | **gpt-transcribe** | **0.0045** | OpenAI's recommended model for recorded speech; **default** |
   | gpt-4o-transcribe, Whisper | 0.006 | more expensive than gpt-transcribe, no advantage for us |
   | gpt-live-transcribe, gpt-realtime-whisper | 0.017 | realtime streaming; WhatsApp sends finished files, so pure waste |
   | gpt-4o-transcribe-diarize | 0.006 | speaker labels; single-speaker voice notes don't need it |

   Cost at 10 voice notes/day × 20 s × 22 days ≈ 73 min/rep/month: **$0.33** (gpt-transcribe) vs $0.22 (mini). The $0.11 gap is small against the
   G6 budget (LLM ≤ $1.50/rep/month), so we pay for quality. Switch with `TRANSCRIBE_MODEL` if the benchmark says mini is as good.
4. **Always decode to 16 kHz mono WAV with ffmpeg before upload.** OpenAI's docs list mp3/mp4/mpeg/mpga/m4a/wav/webm, not OGG. This also gives an
   exact duration, so `TRANSCRIBE_MAX_SECONDS` (180) and the per-user daily budget (`TRANSCRIBE_DAILY_BUDGET_USD`, 0.10) are enforced before spending money.
5. The bot **echoes the transcript** ("🎤 Entendi: …") and high-risk writes still require confirmation, because transcripts can be wrong.
6. Cost per transcription is logged in `app.llm_call` (`purpose='transcribe'`) and shows up in `serving.v_cost_per_user`.

## Consequences
- ffmpeg is now a runtime dependency (Dockerfile and CI install it).
- Audio leaves our infrastructure to OpenAI: add it to the consent text (OPEN-6). Audio is never stored by us; only the transcript flows on (PII-masked before any LLM call).
- **Not verified against the live API**: the only key available for testing had been invalidated. The `languages[]` hint for gpt-transcribe and the
  fallback behaviours are implemented defensively (retry without the hint; fall back to the mini model). Run `scripts/bench_transcribe.py` on 20+ real
  voice notes (incl. noisy ones) before the pilot and confirm the default model.
