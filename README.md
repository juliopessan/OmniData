# OmniData

Inteligência de vendas no WhatsApp, alimentada pelo HubSpot — a primeira fatia de uma visão 360° do cliente.

Este repositório contém:

- **`web/`** — front-end SaaS (landing, funcionalidades, preços, login, cadastro, dashboard) em Next.js 15, com o design system **Ledger** (verde-menta = medido, argila = não verificado, reservados).
- **`src/omnidata/` + `supabase/migrations/`** — back-end **M0** (Python 3.12): migrations bronze/silver/app, cliente HubSpot resiliente, ingestão (backfill retomável, incremental, histórico de propriedades, snapshots), `omnidata audit`, `dev seed` e backup.

Ainda não implementado (M1+): dbt/gold, orquestrador e webhook do WhatsApp, alertas, escritas no HubSpot.

## Back-end (M0)

```bash
uv sync --extra dev
cp .env.example .env            # preencha DATABASE_URL e HUBSPOT_ACCESS_TOKEN
uv run omnidata db migrate
uv run omnidata dev seed        # CRM sintético, sem PII
uv run omnidata audit           # relatório de prontidão + go/no-go
uv run omnidata audit properties && uv run omnidata ingest backfill   # requer token do HubSpot
make check                      # ruff + mypy + pytest
```

Os testes de integração precisam de Postgres (`TEST_DATABASE_URL`); sem ele, são ignorados. O cliente HubSpot foi testado apenas contra fixtures e um HubSpot falso — **nunca rodou contra a API real** (OPEN-1: escopos do private app).

## Front-end

```bash
cd web && npm install && npm run dev   # http://localhost:3000
```

## Rotas

| Rota | Conteúdo |
|---|---|
| `/` | Landing com livro-razão calculado a partir de dados sintéticos |
| `/funcionalidades` | Blocos por tema com exemplos de conversa no WhatsApp (filtro por tema) |
| `/precos`, `/login`, `/cadastro` | Preços ilustrativos; login/cadastro **sem autenticação real** |
| `/dashboard/*` | Visão geral, negócios, alertas, WhatsApp, qualidade dos dados |

Cada rota tem `<title>` e favicon próprios (`web/src/app/**/icon.svg`). O efeito de verbos girando está em `web/src/components/SpinVerb.tsx`.

## Dados

`web/src/lib/seed.ts` (24 negócios sintéticos) → `web/src/lib/metrics.ts` (win rate, IC de Wilson, saúde do negócio, attention_score).
Todo número exibido é calculado ali; nada é digitado no JSX.
