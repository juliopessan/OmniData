# Go-live runbook — what only an account owner can do

Code is done and tested against mocks. §2 (WhatsApp) has been exercised against real services and is in production; the rest has not. Do these in order.

## 1. HubSpot (OPEN-1)
1. Create a **private app**. Scopes (least privilege): `crm.objects.deals.read/write`, `crm.objects.contacts.read`, `crm.objects.companies.read`,
   `crm.objects.owners.read`, `crm.schemas.deals.read`, `crm.objects.notes.write`... plus `tasks` read/write. Confirm names in HubSpot's scope list.
2. Put the token in `HUBSPOT_ACCESS_TOKEN`. Run `omnidata audit properties` and fix `config/hubspot_properties.yaml` for anything reported MISSING.
3. Verify association type ids in `crm/hubspot/writeback.py` (note→deal 214, task→deal 216) with one manual note creation.
4. `omnidata ingest backfill --months 24` then `omnidata audit` (go/no-go per use case).

## 2. WhatsApp via Evolution API (OPEN-9, ADR 0008) — done, verified in production 2026-09-23
No Meta Business verification, no template approval: this is the WhatsApp Web protocol (Baileys), self-hosted, not the
official Cloud API. That trade means less friction to get connected, but it is not Meta's sanctioned integration path —
review the risk in ADR 0008 before using a number that matters.
1. Have a running Evolution API server and its global key → `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`. Invent a random
   value for `EVOLUTION_WEBHOOK_SECRET` (e.g. `openssl rand -hex 32`) — Evolution has no native webhook signature, this
   header is the only thing standing between `/webhooks/evolution` and anyone who finds the URL.
2. `omnidata evolution create-instance --name omnidata --webhook-url https://<api-host>/webhooks/evolution` saves a QR
   code (default `evolution-qrcode.png`) — open it and scan with WhatsApp on the number that will run the bot (Settings
   → Linked Devices → Link a Device). Poll `omnidata evolution status --name omnidata` until it prints `open`.
3. Put that instance name in `EVOLUTION_INSTANCE`. Host the API somewhere with a real domain — [docs/deploy-vps.md](docs/deploy-vps.md)
   is the exact recipe used for the production deploy (a VPS that already runs Traefik + a shared Postgres).
4. Invite a test user: `omnidata user invite --phone +55... --owner <hs_owner_id> --name Ana`; reply **Aceito** on WhatsApp.

**Verified end to end (real WhatsApp instance, production VPS, real DeepSeek calls, 0 errors across 10 messages):**
registration, activation, and Vega/Lyra/Altair/Argus each answering a real question with real (synthetic-seed) data.
The docs' contradictions turned out to matter in one place: `POST /webhook/set/{instance}` rejects the flat body some
pages show — it must nest under `{"webhook": {...}}` (fixed in `EvolutionAdminClient.set_webhook`). Still unverified:
audio (voice notes), group messages, button/list replies, and any write action (`add_note`/`create_task`/confirmation)
— send yourself one of each and check `app.wa_message`/`app.agent_step` before trusting them.

## 3. LLM and voice notes (OPEN-7, ADR 0004)
- Chat: `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` (default), or `openai` + `OPENAI_API_KEY`, `OPENAI_MODEL_ROUTER`, `OPENAI_MODEL_NARRATOR`.
  Without a key the bot runs in degraded keyword/menu mode. `LLM_PROVIDER=deepseek` also works (set `DEEPSEEK_API_KEY` and the two model ids; list them with `curl -H "Authorization: Bearer $DEEPSEEK_API_KEY" https://api.deepseek.com/models`). Before real traffic, decide whether tool JSON (deal and company names) may go to that provider: it is a third party outside your control (LGPD). **No Azure.**
- Fallback: set `OPENROUTER_API_KEY` + `OPENROUTER_MODEL_ROUTER` + `OPENROUTER_MODEL_NARRATOR` to try OpenRouter automatically when the primary provider errors (network, rate limit, 5xx) — never before, and never for a plan the code itself rejects. Same LGPD caveat as above: it's another third party, and it may in turn route to yet other model providers depending on the model id you pick (openrouter.ai/models). With no primary key set, OpenRouter alone becomes the provider.
- Voice notes: set `OPENAI_API_KEY` (transcription works with either chat provider). Default model `gpt-transcribe`. ffmpeg must be installed (the Docker image has it).
- Put keys in your secret manager / Vercel env, **never in chats, commits or `.env` files that are committed**. A key pasted in a chat should be treated as leaked and rotated.
- Before the pilot: `uv run python scripts/bench_transcribe.py samples/` on 20+ real WhatsApp voice notes.

## 4. Database and hosting (D3, OPEN-10)
- Use **Supabase Pro** before real PII (free tier: no backups, pauses when idle). `DATABASE_URL` = transaction pooler, `DATABASE_URL_DIRECT` = direct.
- `omnidata db migrate`, then `docker compose up -d` (api + worker) on any container host. `/healthz` and `/readyz` are the probes.
- Run a **restore drill** from `omnidata db backup` before the pilot (M1 exit).

## 5. Before real reps (OPEN-6)
Legal sign-off on LGPD basis/retention; import quotas: `omnidata quota import quotas.csv` (owner,period_start,period_end,amount).

## 6. Dataset upload and Airbyte (optional)
- Upload: set `ADMIN_API_TOKEN` (long random), `CORS_ORIGINS` (your site origin) and, in the web build, `NEXT_PUBLIC_API_URL`. Until login is real, the token is the only protection: keep it secret and add rate limiting at your proxy.
- Airbyte: follow `docs/airbyte.md`. Not exercised against a real Airbyte yet: run one test sync and `omnidata airbyte ingest` and compare counts with HubSpot before switching `INGEST_MODE`.
