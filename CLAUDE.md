# CLAUDE.md — omnidata
Purpose: WhatsApp sales assistant on a HubSpot-fed Postgres store. Source of truth for scope: PRD-omnidata.md (§ references below).

## Layout
- `src/omnidata/` Python backend (M0: ingestion, audit, seed, backup). `supabase/migrations/` forward-only SQL.
- Harness (ADR 0003): `agents/team.py` (roster + tool allowlists = source of truth; `omnidata team export > web/src/lib/team.json`), `agents/orion.py` (plan validation).
- Bot (M1): `bot/` (orchestrator, actions, repo, `gateway.py` = MessagingGateway Protocol only, `evolution.py` = Evolution API impl + instance lifecycle (ADR 0008), webhook, `sentiment.py` = deterministic tone signal — never an LLM call — for a "digitando..." pause (`TYPING_DELAY_MAX_SECONDS`, off by default), a 👍 reaction on a bare "valeu" instead of the menu, and a persona hint that only ever shapes tone, never a fact), `llm/` (chat: anthropic|openai|deepseek (OpenAI-compatible, own key/URL/models; audio keeps OPENAI_API_KEY); `fallback.py`: FallbackLlmClient tries OpenRouter after the primary errors, never before, never on a rejected plan — wired in `jobs/worker.build_llm`; `transcribe.py`: OpenAI speech-to-text, ADR 0004; no Azure), `alerts/`, `api/`, `jobs/worker.py`; gold/serving are SQL views (ADR 0002).
- Data in: `datasets/` (CSV/XLSX upload, one canonical importer, ADR 0005), `integrations/airbyte/` (Airbyte landing + generic mapping, ADR 0006), `api/datasets.py`. Regenerate the web spec: `omnidata dataset spec > web/src/lib/dataset-spec.json`.
- Observabilidade: `telemetry.py` (Langfuse, self-hosted; degrade-to-off como qualquer outra integração opcional se `LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL` faltarem). Um trace por mensagem WhatsApp (`bot/orchestrator.py::handle`, span "handle-message", `user_id`/`session_id` = id interno, nunca o telefone), com generations para roteamento do Orion (`route-request`), narração por especialista (`narrate-response`) e transcrição de áudio, mais um observation `tool` por step do `run_plan`. Só passa texto já mascarado por `mask_pii`.
- Insights: `insights/` (spec + compute, puro e determinístico; `omnidata insights spec > web/src/lib/insights-spec.json`), views `serving.v_deal_facts|v_deal_notes` (0009), 7 tools `get_pains…get_insight_digest`; port TS em `web/src/lib/insights.ts` (mesmo spec).
- Routing without LLM is `bot/routing.py` (pure; used by the orchestrator AND `evals/planner.py`); keyword rules in `bot/router.py`. Writes never fall back to a read.
- Forecast (Vega `get_forecast`): `forecast/` (pure statistical layer; ML gate `ml_status`, layer 2 NOT built, ADR 0007); TS port `web/src/lib/forecast.ts` (standalone, same PRNG; a test runs it in Node and compares bit for bit). Never show a probability below `MIN_CLOSED`; flag `backlog`.
- Coach (Polaris): `hygiene/` (spec + compute, puro; `omnidata hygiene spec > web/src/lib/hygiene-spec.json`), view `serving.v_hygiene_facts` (0010), tool `get_fix_queue` (read-only; fixes go through Lyra); port TS em `web/src/lib/hygiene.ts`.
- Coach de vendas (Nova): tools `get_playbook` (reaproveita `repo.insight_analysis`: motivos de perda, dores, termos) e `search_meeting_notes` (também dona do Atlas — primeira ferramenta com dois donos legítimos; `_run_tool` assina com o agente que o Orion realmente planejou, não mais um dono único fixo). Nunca conselho inventado, só o que já está registrado.
- Status do time p/ gestores (Vega): tool `get_team_status`, `repo.team_status` agrega `serving.v_rep_kpis` + `serving.v_hygiene_facts` por dono, ordenado do atingimento mais baixo ao mais alto; sem lógica de permissão própria, `Principal.owner_clause()` já reduz um vendedor comum a só ele mesmo.
- Meta pessoal (Aurora): tools `set_goal`/`get_goal_status`, tabela `app.seller_goal` + `serving.v_seller_goal`. Conjunto fechado de tipos mensuráveis (`deals_won`, `quota_pct`) e prazo em dias (`deadline_in_days`, mesmo padrão de `CreateTask.due_in_days`) — nunca um objetivo livre que o LLM teria que julgar. `set_goal` é escrita local (não CRM), roda antes do gate `deps.writer`. `get_morning_brief` inclui a linha da meta quando há uma ativa.
- Sugestões proativas: determinísticas, condicionadas a dado real (nunca o LLM inventando) — `tpl_attention`/`tpl_brief` sugerem a Polaris quando `repo.fix_queue` tem item pendente; `tpl_playbook` (objeção) sempre sugere a Lyra quando há dado. `tpl_brief` também é sensível à hora (`Bom dia`/`Boa tarde`/`Boa noite`, via `deps.settings.app_timezone`).
- Recapitulação às 18h (Aurora): `alerts/engine.py::evening_recaps`, mesmo molde de `morning_briefs` (gate por hora local, dedupe diário via `audit_log`), mas manda o texto pronto direto (`send_text`, sem template+botão). View `serving.v_activity` (0014) só pra isso. Job `recap` em `jobs/worker.py`.
- `run_plan` não repete a assinatura (`*Agente*:`) quando dois passos seguidos do plano caem no mesmo especialista.
- Orion resolutivo: `_orion` manda pro roteador a última troca completa (`_recent_context`, só 1 turno, nunca a mensagem em processamento) rotulada "Contexto da última troca", separada do "Pedido atual" — resolve referências tipo "isso"/"essas causas" sem dar memória de sessão ao roteador. `get_playbook` no catálogo explica quando usar cada `topic` (antes o LLM chutava "pitch" pra pedidos de "reunião difícil").
- Memória de reuniões (Atlas, ADR 0009): `rag/` (embeddings.py, chroma.py — clientes síncronos, mesmo padrão de `repo.py`), `transcripts/` (synth.py = transcrições sintéticas sobre negócios reais; ingest.py = embed + upsert no Chroma), tabela `app.meeting_transcript` + `serving.v_meeting_transcript`, tool `search_meeting_notes`. Chroma é só índice semântico; a permissão é sempre decidida de novo no Postgres via `Principal.owner_clause()` antes de qualquer trecho virar resposta (regra 7). CLI: `omnidata transcripts seed|search`.
- Propostas (Vela): tool `send_proposal` (nunca toca o HubSpot — roda antes do gate `deps.writer`, igual `set_goal`). `mailer/gmail.py`: dois envios atrás da mesma interface `EmailSender`, escolhidos em `jobs/worker.py::build_emailer` por qual credencial existe — `GmailApiSender` (Gmail API + OAuth2, `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN`, preferido; o refresh token sai de `scripts/gmail_oauth_setup.py`, rodado uma vez) ou `GmailSmtpSender` (SMTP + app password, fallback). Tudo vazio = degrada pra só WhatsApp. `proposals/` (`template.py` Jinja2 sobre `templates/proposal.html` — tabelas, não flexbox nem `<section>` sem `display`, porque o WeasyPrint 62.x tem suporte parcial a ambos; `pdf.py` WeasyPrint). `PROPOSAL_COMPANY_NAME` assina o PDF (a empresa do vendedor, nunca "OmniData" hardcoded) e `PROPOSAL_LOGO` (caminho de arquivo; vazio = monograma) vai no papel timbrado; o nº da proposta é o id do `pending_action` (mesma referência do `audit_log`). O cliente nunca vê o rótulo cru do CRM: título, assunto do e-mail e nome do arquivo usam `proposals.template.client_name()`, que reaproveita `insights.compute.company()`. `channel="whatsapp"` (PDF volta só pro próprio vendedor) gera e manda na hora (`send_proposal_to_self`), sem confirmação; e-mail (sai pro cliente) é escrita de alto risco (`propose_send_proposal`/`confirm_send_proposal` em `actions.py`), com confirm próprio — `actions.confirm()` é hard-coded pro update_deal, então `_handle_reply_id`/`_free_text_confirmation` despacham por `pending_action.kind` antes de chamar um ou outro. Sem Undo (nada a desfazer depois de enviado). `send_document` em `gateway.py`/`evolution.py` (`/message/sendMedia`, corpo `mediatype`/`fileName`/`media` base64) verificado contra a instância real em 25/09/2026, junto com o envio pela Gmail API.
- Botões/listas saem como texto numerado (Evolution); `send` grava as opções no payload de saída e `_numbered_option` traduz a resposta "1"/título de volta pro reply id antes do LLM.
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
