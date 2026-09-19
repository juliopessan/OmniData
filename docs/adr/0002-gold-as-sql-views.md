# ADR 0002: gold layer as plain SQL views for M1 bootstrap (deviation from D12)
- Status: accepted (interim) · Date: 2026-09-20 · Decision-log row: D12 (dbt-core for silver→gold)

## Context
D12 locks dbt-core for gold. M1 needs a working `serving.*` read contract now, and the environment has no dbt/Docker toolchain wired up yet.
## Decision
Implement `gold.*` and `serving.*` as SQL views in `supabase/migrations/0006_gold_serving.sql`. Same column contract as PRD §9, computed live from silver.
## Consequences
Views recompute on read (fine at MVP volume; materialize if slow). The bot only depends on `serving.*`, so moving these models into `dbt/` later changes nothing for callers. Tracked: port to dbt with tests (unique/not_null/accepted_values) before the real-rep pilot.
