# ADR 0008: Evolution API (Baileys, self-hosted) replaces the Meta Cloud API as the WhatsApp gateway
- Status: accepted · Date: 2026-09-22 · Decision-log row (PRD §5): D15 (superseded)

## Context
D15 picked the Meta WhatsApp Cloud API (`bot/gateway.py`'s `WhatsAppCloudGateway`), behind a `MessagingGateway` interface specifically so the BSP could be swapped later. Meta Business verification and message-template approval were the slowest step of go-live (`docs/go-live.md` §2) and had not been done. The user already runs a self-hosted Evolution API instance (Node.js, Baileys/WhatsApp Web protocol) with URL and global key in hand, and asked to switch — n8n was considered and rejected: the harness's guarantees (idempotent inbound dedupe, Principal-scoped permissions, per-agent tool allowlists, the number guard, `pending_action` confirmation) live in tested Python code, and a workflow tool in the middle would either bypass them or just re-implement the same webhook call with none of the tests.

Evolution API is not Meta's sanctioned integration: it automates the WhatsApp Web protocol rather than using the official Business API, so there is a real risk of the number being restricted or banned that the Cloud API does not carry, and there is no first-party message-template mechanism outside a 24-hour session window. This was told to the user explicitly before implementing.

## Decision
`bot/gateway.py` now holds only the provider-neutral `MessagingGateway` Protocol and `GatewayError`. `bot/evolution.py` adds:
- `EvolutionAdminClient` — instance lifecycle (create, QR code, connection state, webhook config, delete, list), scripting what the Evolution Manager UI does by hand. Exposed as `omnidata evolution create-instance|qrcode|status|set-webhook|list-instances|delete-instance`.
- `EvolutionGateway` — the runtime `MessagingGateway`: `send_text` documented and used for everything, including onboarding (no more Cloud API templates — `strings_ptbr.ONBOARDING_ASK` sent as plain text). `send_buttons`/`send_list` degrade to numbered plain text (`_numbered_text`): Baileys' native interactive UI has been unreliable since WhatsApp limited it to the official Business API. The reply id stays the visible option number, so the existing button/list reply handling in the orchestrator needs no change.

Webhook: `/webhooks/evolution` replaces `/webhooks/whatsapp`. Evolution has no request signature (unlike Meta's `X-Hub-Signature-256`); `EVOLUTION_WEBHOOK_SECRET` is a value we invent, set into Evolution's webhook config as a custom header (`X-OmniData-Secret`), and check constant-time on receipt — same shape as the admin-upload token in `api/guard.py`. Baileys echoes the bot's own sent messages back through the same webhook (`fromMe: true`); `persist_inbound` drops those explicitly, a case a Cloud API integration never had to handle.

Settings: `WHATSAPP_PHONE_NUMBER_ID`/`ACCESS_TOKEN`/`APP_SECRET`/`VERIFY_TOKEN` removed; `EVOLUTION_API_URL`/`API_KEY`/`INSTANCE`/`WEBHOOK_SECRET` added.

## Consequences
Onboarding is faster (scan a QR code instead of Meta Business verification + template review), but the integration now depends on an unofficial protocol the user's Evolution instance implements, and on documentation that visibly disagrees with itself across pages and versions (checked 2026-09-22 at docs.evolutionfoundation.com.br). Two things are marked OPEN-8, unverified against a real instance:
- the exact `send_text` request body and the exact `webhook/set` body (two documented variants exist; `EvolutionAdminClient` uses the best-attested one);
- the exact `MESSAGES_UPSERT` payload field names (no example payload is published; `bot/webhook.py`'s parser is defensive and stores nothing it cannot positively identify, rather than guessing and silently storing the wrong thing).

Before real traffic: send one real text and one real audio message through the connected instance and diff the actual webhook payload against `message_kind()` in `bot/webhook.py`, the same discipline `omnidata audit properties` applies to HubSpot field names (CLAUDE.md rule 2) and ADR 0006 applied to Airbyte ("never ran against a real Airbyte — run a test sync before trusting"). `download_media` (voice notes) carries the same caveat and fails as a clean, already-tested `GatewayError` ("não consegui entender o áudio") rather than crashing if the endpoint guess is wrong.
