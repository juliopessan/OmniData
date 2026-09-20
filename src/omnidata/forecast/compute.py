"""Statistical forecast of what the open pipeline can still add, and the chance of reaching a target. Pure, no I/O, no LLM.
Method (layer 1, explainable and honest with small samples):
  * win rate p = wins / closed, with a Wilson 95% interval [lo, hi];
  * each open deal WITH a value wins with probability p (the same p for all: there is no stage history to do better);
  * three scenarios (p = lo, mid, hi) are simulated with the SAME random numbers, so low <= mid <= high in every trial;
  * the generator is a fixed-seed mulberry32, reproduced bit for bit in TypeScript (web/src/lib/forecast.ts).
Known bias: the rate comes only from CLOSED deals; deals that stall or are abandoned never appear as lost, so p tends to be optimistic.
When the open deals with value outnumber the closed ones by more than BACKLOG_RATIO the result is flagged `backlog` and shown as indicative only."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from ..metrics import wilson
from . import spec

_M = 0xFFFFFFFF


def mulberry32(seed: int) -> Callable[[], float]:
    """Same algorithm as the JS one-liner; uniform in [0, 1)."""
    a = seed & _M

    def rnd() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & _M
        t = a
        t = ((t ^ (t >> 15)) * (t | 1)) & _M
        t = (t ^ ((t + (((t ^ (t >> 7)) * (t | 61)) & _M)) & _M)) & _M
        return ((t ^ (t >> 14)) & _M) / 4294967296
    return rnd


def trials_for(n_deals: int) -> int:
    return min(spec.TRIALS, max(spec.MIN_TRIALS, spec.MAX_DRAWS // max(1, n_deals)))


def _quantile(sorted_vals: list[float], q: float) -> float:
    return sorted_vals[int(q * (len(sorted_vals) - 1))]


def _totals(amounts: list[float], p: float, trials: int, seed: int) -> list[float]:
    rnd = mulberry32(seed)
    out = []
    for _ in range(trials):
        s = 0.0
        for a in amounts:
            if rnd() < p:
                s += a
        out.append(s)
    return out


def ml_status(closed: int, has_created_at: bool = False, has_stage_history: bool = False, min_closed: int = spec.ML_MIN_CLOSED) -> dict[str, Any]:
    """Layer 2 (a scikit-learn classifier) is NOT implemented. This says what the data still lacks before it may be built.
    Planned: logistic regression / gradient boosting on features known BEFORE the close, time-ordered validation, calibration,
    and it ships only if it beats this statistical forecast on the same held-out period."""
    missing = []
    if closed < min_closed:
        missing.append(f"pelo menos {min_closed} negócios fechados (há {closed})")
    if not has_created_at:
        missing.append("data de criação dos negócios")
    if not has_stage_history:
        missing.append("histórico de etapas (para usar só o que existia antes do fechamento)")
    return {"implemented": False, "data_ready": not missing, "missing": missing}


def forecast(open_amounts: Iterable[float], wins: int, losses: int, realized: float = 0.0, quota: float | None = None,
             *, has_created_at: bool = False, has_stage_history: bool = False) -> dict[str, Any]:
    amounts = sorted((float(a) for a in open_amounts if a and float(a) > 0), reverse=True)
    closed = wins + losses
    base: dict[str, Any] = {"closed": closed, "wins": wins, "losses": losses, "open_with_value": len(amounts), "open_amount": sum(amounts),
                            "realized": realized, "quota": quota, "min_closed": spec.MIN_CLOSED,
                            "ml": ml_status(closed, has_created_at, has_stage_history)}
    if closed < spec.MIN_CLOSED:
        return {**base, "status": "insufficient"}
    if not amounts:
        return {**base, "status": "no_pipeline"}
    lo, hi = wilson(wins, closed)
    rate = wins / closed
    target = max(quota - realized, 0.0) if quota is not None else None
    trials = trials_for(len(amounts))
    total = sum(amounts)
    scenarios: dict[str, Any] = {}
    for name, p in (("low", lo), ("mid", rate), ("high", hi)):
        t = sorted(_totals(amounts, p, trials, spec.SEED))
        sc: dict[str, Any] = {"p": p, "expected": p * total, "p10": _quantile(t, 0.10), "p50": _quantile(t, 0.50), "p90": _quantile(t, 0.90)}
        if target is not None:
            sc["prob_target"] = 1.0 if target <= 0 else sum(1 for x in t if x >= target) / len(t)
        scenarios[name] = sc
    backlog = len(amounts) > spec.BACKLOG_RATIO * closed   # far more open deals than history: most will never close, the rate overstates them
    return {**base, "status": "indicative" if (closed < spec.INDICATIVE_CLOSED or backlog) else "ok", "backlog": backlog, "win_rate": rate, "win_rate_ci": [lo, hi],
            "trials": trials, "target": target, "scenarios": scenarios}
