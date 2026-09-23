# CLAUDE.md — omnidata
Purpose: WhatsApp sales assistant on a HubSpot-fed Postgres store. Source of truth for scope: PRD-omnidata.md (§ references below).

## Layout
- `src/omnidata/` Python backend (M0: ingestion, audit, seed, backup). `supabase/migrations/` forward-only SQL.
- Harness (ADR 0003): `agents/team.py` (roster + tool allowlists = source of truth; `omnidata team export > web/src/lib/team.json`), `agents/orion.py` (plan validation).
- Bot (M1): `bot/` (orchestrator, actions, repo, `gateway.py` = MessagingGateway Protocol only, `evolution.py` = Evolution API impl + instance lifecycle (ADR 0008), webhook), `llm/` (chat: anthropic|openai|deepseek (OpenAI-compatible, own key/URL/models; audio keeps OPENAI_API_KEY); `fallback.py`: FallbackLlmClient tries OpenRouter after the primary errors, never before, never on a rejected plan — wired in `jobs/worker.build_llm`; `transcribe.py`: OpenAI speech-to-text, ADR 0004; no Azure), `alerts/`, `api/`, `jobs/worker.py`; gold/serving are SQL views (ADR 0002).
- Data in: `datasets/` (CSV/XLSX upload, one canonical importer, ADR 0005), `integrations/airbyte/` (Airbyte landing + generic mapping, ADR 0006), `api/datasets.py`. Regenerate the web spec: `omnidata dataset spec > web/src/lib/dataset-spec.json`.
- Insights: `insights/` (spec + compute, puro e determinístico; `omnidata insights spec > web/src/lib/insights-spec.json`), views `serving.v_deal_facts|v_deal_notes` (0009), 7 tools `get_pains…get_insight_digest`; port TS em `web/src/lib/insights.ts` (mesmo spec).
- Routing without LLM is `bot/routing.py` (pure; used by the orchestrator AND `evals/planner.py`); keyword rules in `bot/router.py`. Writes never fall back to a read.
- Forecast (Vega `get_forecast`): `forecast/` (pure statistical layer; ML gate `ml_status`, layer 2 NOT built, ADR 0007); TS port `web/src/lib/forecast.ts` (standalone, same PRNG; a test runs it in Node and compares bit for bit). Never show a probability below `MIN_CLOSED`; flag `backlog`.
- Coach (Polaris): `hygiene/` (spec + compute, puro; `omnidata hygiene spec > web/src/lib/hygiene-spec.json`), view `serving.v_hygiene_facts` (0010), tool `get_fix_queue` (read-only; fixes go through Lyra); port TS em `web/src/lib/hygiene.ts`.
- Coach de vendas (Nova): tool `get_playbook`, reaproveita `repo.insight_analysis` (motivos de perda, dores, termos); nunca conselho inventado, só o que já está registrado.
- Status do time p/ gestores (Vega): tool `get_team_status`, `repo.team_status` agrega `serving.v_rep_kpis` + `serving.v_hygiene_facts` por dono, ordenado do atingimento mais baixo ao mais alto; sem lógica de permissão própria, `Principal.owner_clause()` já reduz um vendedor comum a só ele mesmo.
- Memória de reuniões (Atlas, ADR 0009): `rag/` (embeddings.py, chroma.py — clientes síncronos, mesmo padrão de `repo.py`), `transcripts/` (synth.py = transcrições sintéticas sobre negócios reais; ingest.py = embed + upsert no Chroma), tabela `app.meeting_transcript` + `serving.v_meeting_transcript`, tool `search_meeting_notes`. Chroma é só índice semântico; a permissão é sempre decidida de novo no Postgres via `Principal.owner_clause()` antes de qualquer trecho virar resposta (regra 7). CLI: `omnidata transcripts seed|search`.
- `web/` Next.js front-end (landing, auth, dashboard) with the Ledger design system; synthetic data only.

## Commands
- make check      # ruff + mypy + pytest (must pass before any commit; dbt build arrives with M1)
- omnidata serve api | omnidata serve worker | omnidata user invite|erase | omnidata quota import <csv>
- make migrate    # apply supabase/migrations  (uv run omnidata db migrate)
- omnidata audit | omnidata audit properties | omnidata ingest backfill | omnidata ingest incremental | omnidata dev seed
- omnidata dataset import|template|spec | omnidata airbyte connections|sync|ingest|generic
- omnidata insights spec|analyze <file> | omnidata hygiene spec|analyze <file>
- omnidata forecast analyze <file> [--quota N --realized N]
- omnidata evolution create-instance|qrcode|status|set-webhook|list-instances|delete-instance (ADR 0008)
- omnidata eval planner [--mode keyword|llm] [--cases f.yaml]   # planner golden set (src/omnidata/evals); keyword rules must not be tuned on planner_holdout.yaml
- omnidata db backup | omnidata db size-report
- Tests need Postgres: `TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:54399/omnidata_test` (DB tests skip if unreachable)
- web: `cd web && npm install && npm run dev`. Build de teste em paralelo ao dev server: `NEXT_DIST_DIR=.next-x NEXT_TSCONFIG=tsconfig.iso.json` (com `tsconfig.iso.json` = `{ "extends": "./tsconfig.json" }`, ignorado pelo git); assim o `.next` e o `tsconfig.json` não mudam.

## Rules
1. Plan first for any task touching more than 3 files; small commits referencing FR-IDs.
2. Never assume HubSpot property names; run `omnidata audit properties` and use discovered names (config/hubspot_properties.yaml).
3. Agents: the LLM proposes plans, code validates them (allowlist, <=3 steps, <=1 write, last). Never let a specialist call a tool outside its list. The LLM never does arithmetic, never writes SQL, never receives raw PII. Numbers shown to users come from tool JSON.
4. All CRM writes go through pending_action + audit_log with idempotency keys; high-risk writes need confirmation.
5. Bot-facing text lives only in bot/strings_ptbr.py.
6. Migrations are forward-only. Never edit an applied migration.
7. Permissions are enforced in repositories via Principal. No tool accepts an owner id from model output.
8. HTTP bodies: auth and size limits run BEFORE the body is read (`api/guard.py`, pure ASGI); FastAPI parses forms before dependencies, so a check inside a route is too late. New POST routes with bodies must be added there. Web security headers live in `web/next.config.mjs` (CSP only in production).
8b. No PII in logs. No secrets in the repo.
9. Unresolved [OPEN-n] items: implement behind an interface or config flag, add a TODO(OPEN-n), continue.
10. To change a decision in §5, add an ADR (docs/adr) and a row to the decision log in the same PR.

## Definition of done
- make check passes; new behavior has tests including a negative case; test names reference the FR-ID.
- After any rename or removal, grep the repo for residual references.
- Docs updated: README, docs/, .env.example.
