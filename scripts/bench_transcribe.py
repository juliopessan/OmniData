#!/usr/bin/env python
"""Compare transcription models on YOUR WhatsApp audio. Uses the production code path (OGG -> WAV -> API).

  export OPENAI_API_KEY=...            # from your secret manager; never paste keys into chats or commit them
  uv run python scripts/bench_transcribe.py samples/ [gpt-transcribe gpt-4o-mini-transcribe gpt-4o-transcribe]

`samples/` holds pairs: `<name>.ogg` (a real voice note, exported from WhatsApp) and `<name>.txt` (what was actually said).
Prints word error rate (lower is better), latency and estimated cost per model. Use 20+ clips incl. noisy ones before deciding."""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from omnidata.llm.transcribe import OpenAITranscriber, TranscribeError

DEFAULT_MODELS = ["gpt-transcribe", "gpt-4o-mini-transcribe", "gpt-4o-transcribe"]


def words(s: str) -> list[str]:
    return re.sub(r"[^\w\s]", "", s.lower()).split()


def wer(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    dp = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, len(h) + 1):
            cur = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return dp[len(h)] / max(1, len(r))


async def main(folder: Path, models: list[str]) -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("set OPENAI_API_KEY")
    clips = sorted(p for p in folder.glob("*.ogg") if p.with_suffix(".txt").exists())
    if not clips:
        sys.exit(f"no <name>.ogg + <name>.txt pairs in {folder}")
    print(f"{len(clips)} clips\n{'model':26s} {'WER':>7s} {'p50 lat':>9s} {'cost/min':>9s} {'failed':>6s}")
    for model in models:
        t = OpenAITranscriber(key, model, fallback_model="")  # no fallback: measure exactly this model
        errs, lats, cost, secs, failed = [], [], 0.0, 0.0, 0
        for c in clips:
            try:
                r = await t.transcribe(c.read_bytes())
            except TranscribeError:
                failed += 1
                continue
            errs.append(wer(c.with_suffix(".txt").read_text(), r.text))
            lats.append(r.latency_ms / 1000)
            cost += r.cost_usd
            secs += r.seconds
        p50 = sorted(lats)[len(lats) // 2] if lats else float("nan")
        per_min = (cost / (secs / 60)) if secs else float("nan")
        print(f"{model:26s} {sum(errs) / max(1, len(errs)):7.3f} {p50:8.2f}s {per_min:9.4f} {failed:6d}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2:] or DEFAULT_MODELS))
