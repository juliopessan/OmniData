"""Forecast limits, in one place (mirrored by web/src/lib/forecast.ts; a test keeps them equal)."""
from __future__ import annotations

MIN_CLOSED = 10          # below this many closed deals there is no forecast at all
INDICATIVE_CLOSED = 20   # below this the forecast is shown as indicative only (same idea as MIN_N_RANKING)
TRIALS = 4000            # simulated outcomes per scenario
MAX_DRAWS = 4_000_000    # trials shrink when there are many open deals, to keep the run fast
MIN_TRIALS = 200
SEED = 20260920          # fixed: the same data always gives the same answer
BACKLOG_RATIO = 3        # more than this many open deals (with value) per closed deal: the win rate of the past does not describe the backlog
ML_MIN_CLOSED = 300      # PRD gate for a predictive model (config: MODEL_MIN_CLOSED)


def spec_json() -> dict[str, int]:
    return {"minClosed": MIN_CLOSED, "indicativeClosed": INDICATIVE_CLOSED, "trials": TRIALS, "maxDraws": MAX_DRAWS, "minTrials": MIN_TRIALS, "seed": SEED, "backlogRatio": BACKLOG_RATIO}
