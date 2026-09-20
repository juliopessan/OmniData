# ADR 0003: bounded agentic harness — "Observatório" (amends D7)
- Status: accepted · Date: 2026-09-20 · Decision-log row: **D7 amended** (was: deterministic orchestrator, LLM only at tool selection + narration)

## Context
The product should feel like an office of assessors in WhatsApp: a coordinator reads the request, splits it, and the right specialist answers, each signing their own work.
D7 forbade free-running agent loops for cost, auditability and safety. We keep those goals.

## Decision
A **bounded** multi-agent harness:
- **Orion** (coordinator) asks the LLM for a *plan* (`plan` tool call): 1–3 steps, each `{specialist, tool, args}`. Code validates it (`agents/orion.py:validate_plan`): specialist exists, tool is in that specialist's allowlist, args pass pydantic, owner scope stripped, **≤ 1 write and it must be last**. Invalid plan → discarded, logged as `rejected`, deterministic keyword route answers instead.
- **Specialists** (Vega, Altair, Lyra, Aurora, Argus, Polaris) each own a fixed set of tools (`agents/team.py`). They execute sequentially, narrate in their own voice through the number guard, and sign the section.
- **No** agent-to-agent calls, **no** recursion, **no** loops. Max 3 steps per message. Token budget and rate limit unchanged.
- Writes keep FR-WRT rules: low-risk executes with receipt/Undo, high-risk needs confirmation.
- Users can address a member directly ("Vega, ..."); the plan is then restricted to that member.
- Degraded mode (no LLM) stays deterministic: keyword → one specialist.
- Telemetry `app.agent_step` stores agent, tool, status, latency only (no arguments, no text).

## Consequences
+ More natural multi-part requests; clear ownership and audit trail per agent.
− One extra LLM call per free-text message (planner). Mitigation: plans are ≤ 3 steps and keyword routing skips the LLM when there is none.
− Planner quality is a new eval target: add plan-accuracy cases to `tests/evals` (router set ≥ 100 utterances) before the pilot. **Not yet done.**

## Addendum: Polaris, the Coach (2026-09-20)
A seventh member. Argus measures data quality; Polaris turns the measurement into a short, value-ordered fix queue per seller (`get_fix_queue`, read-only, computed in `hygiene/compute.py` from `serving.v_hygiene_facts`). Rules: (1) Polaris never writes; every fix is registered by Lyra through `pending_action` with confirmation; (2) a gap present in >= 90% of open deals is reported as *systemic* (likely export or CRM default) and is only asked of deals with value; (3) inactive owners and duplicates are shown to managers/admins only; (4) it is a data-hygiene coach, not a sales-call coach (script adherence stays no-go: no transcripts, OPEN-4).
