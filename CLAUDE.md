# CLAUDE.md — omnidata
Purpose: WhatsApp sales assistant on a HubSpot-fed Postgres store. Source of truth for scope: PRD-omnidata.md (§ references below).

## Layout
- `src/omnidata/` Python backend (M0: ingestion, audit, seed, backup). `supabase/migrations/` forward-only SQL.
- Harness (ADR 0003): `agents/team.py` (roster + tool allowlists = source of truth; `omnidata team export > web/src/lib/team.json`), `agents/orion.py` (plan validation).
- Bot (M1): `bot/` (orchestrator, actions, repo, gateway, webhook), `llm/` (chat: anthropic|openai; `transcribe.py`: OpenAI speech-to-text, ADR 0004; no Azure), `alerts/`, `api/`, `jobs/worker.py`; gold/serving are SQL views (ADR 0002).
- `web/` Next.js front-end (landing, auth, dashboard) with the Ledger design system; synthetic data only.

## Commands
- make check      # ruff + mypy + pytest (must pass before any commit; dbt build arrives with M1)
- omnidata serve api | omnidata serve worker | omnidata user invite|erase | omnidata quota import <csv>
- make migrate    # apply supabase/migrations  (uv run omnidata db migrate)
- omnidata audit | omnidata audit properties | omnidata ingest backfill | omnidata ingest incremental | omnidata dev seed
- omnidata db backup | omnidata db size-report
- Tests need Postgres: `TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:54399/omnidata_test` (DB tests skip if unreachable)
- web: `cd web && npm install && npm run dev`

## Rules
1. Plan first for any task touching more than 3 files; small commits referencing FR-IDs.
2. Never assume HubSpot property names; run `omnidata audit properties` and use discovered names (config/hubspot_properties.yaml).
3. Agents: the LLM proposes plans, code validates them (allowlist, <=3 steps, <=1 write, last). Never let a specialist call a tool outside its list. The LLM never does arithmetic, never writes SQL, never receives raw PII. Numbers shown to users come from tool JSON.
4. All CRM writes go through pending_action + audit_log with idempotency keys; high-risk writes need confirmation.
5. Bot-facing text lives only in bot/strings_ptbr.py.
6. Migrations are forward-only. Never edit an applied migration.
7. Permissions are enforced in repositories via Principal. No tool accepts an owner id from model output.
8. No PII in logs. No secrets in the repo.
9. Unresolved [OPEN-n] items: implement behind an interface or config flag, add a TODO(OPEN-n), continue.
10. To change a decision in §5, add an ADR (docs/adr) and a row to the decision log in the same PR.

## Definition of done
- make check passes; new behavior has tests including a negative case; test names reference the FR-ID.
- After any rename or removal, grep the repo for residual references.
- Docs updated: README, docs/, .env.example.
