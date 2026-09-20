# ADR 0007: statistical forecast first; ML stays off until the data can support it
- Status: accepted · Date: 2026-09-20 · Related: PRD gate G2 (>= 300 closed deals per pipeline), `MODEL_MIN_CLOSED`

## Context
We want to predict whether a team will reach its quota. The real HubSpot exports we have hold 22 and 33 closed deals, no creation dates, no stage history and no quotas.
A scikit-learn model on that would overfit, and the notes of closed deals include post-close text (loss reasons), so it would learn the outcome (leakage) and look accurate on a random split.

## Decision
Layer 1 (built): `forecast/compute.py`. Win rate from closed deals with a Wilson 95% interval; open deals with a value win with that rate; three scenarios simulated with the same fixed-seed random numbers (mulberry32, reproduced in TypeScript), so low <= mid <= high; results are bands (p10/p50/p90) and P(reaching the target). Guards: no forecast below 10 closed deals; indicative below 20; `backlog` (open with value > 3 x closed) is shown as a ceiling, not a forecast.
Layer 2 (NOT built): a classifier (logistic regression or gradient boosting) on features known before the close, time-ordered validation, calibration; it ships only if it beats layer 1 on the same held-out period. `ml_status()` reports what is missing (>= 300 closed, creation date, stage history).

## Consequences
The forecast is explainable and honest with small samples, but it is coarse: one rate for every open deal (there is no stage history) and biased upward (stalled deals never become lost). The `backlog` guard exists because the second real export (173 open, 33 closed) produced 82% and "100% chance" without it.
To unlock layer 2, ingest creation dates and stage history from HubSpot (the direct client already reads history; it has never run on a real account) and capture loss reasons.
