# OmniData

Inteligência de vendas no WhatsApp, alimentada pelo HubSpot — a primeira fatia de uma visão 360° do cliente.

Este repositório contém:

- **`web/`** — front-end SaaS (landing, funcionalidades, preços, login, cadastro, dashboard) em Next.js 15, com o design system **Ledger** (verde-menta = medido, argila = não verificado, reservados).
- **`src/omnidata/` + `supabase/migrations/`** — back-end **M0** (Python 3.12): migrations bronze/silver/app, cliente HubSpot resiliente, ingestão (backfill retomável, incremental, histórico de propriedades, snapshots), `omnidata audit`, `dev seed` e backup.

Também implementado (M1, **testado só com mocks**): API/webhook do WhatsApp, worker e agendador, orquestrador (LLM só nas pontas), guarda de números, permissões por `Principal`, escritas no HubSpot com recibo/Desfazer/confirmação, alertas, resumo matinal, views `gold`/`serving`. Ver `docs/go-live.md` para o que depende das suas contas (HubSpot, Meta, LLM, Supabase).

### O Observatório (harness agêntico, ADR 0003)

| Membro | Função | Ferramentas |
|---|---|---|
| **Orion** | Coordenador: analisa o pedido, monta o plano (≤ 3 passos) e devolve uma resposta só | — |
| **Vega** | Analista de Metas | `get_kpis`, `get_quota_status` |
| **Altair** | Gerente de Pipeline | `get_pipeline_summary`, `get_deal`, `list_deals_needing_action` |
| **Lyra** | Escriba do CRM (recibo + Desfazer) | `add_note`, `create_task`, `propose_deal_update`, `undo_last` |
| **Aurora** | Rotina e Alertas | `get_morning_brief` |
| **Argus** | Auditor de Confiança | `get_data_quality` |

O LLM só *propõe* o plano; o código valida (allowlist por especialista, no máximo 1 escrita e por último). Endereçamento direto: “Vega, como estou na meta?”. `uv run omnidata team` lista a equipe; `team export` gera `web/src/lib/team.json` (um teste garante a sincronia).

Ainda não implementado: motivo de perda (M2), previsão/modelo (M2), coach e transcrições (M3), dbt (ADR 0002).

## Back-end (M0)

```bash
uv sync --extra dev
cp .env.example .env            # preencha DATABASE_URL e HUBSPOT_ACCESS_TOKEN
uv run omnidata db migrate
uv run omnidata dev seed        # CRM sintético, sem PII
uv run omnidata audit           # relatório de prontidão + go/no-go
uv run omnidata audit properties && uv run omnidata ingest backfill   # requer token do HubSpot
uv run omnidata serve api       # webhook + /healthz + /readyz
uv run omnidata serve worker    # fila de mensagens + ingestão + alertas
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
| `/precos`, `/login`, `/cadastro` | Preços todos “Sob consulta”; login/cadastro **sem autenticação real** |
| `/dashboard/*` | Visão geral, negócios, alertas, WhatsApp, qualidade dos dados |

Cada rota tem `<title>` e favicon próprios (`web/src/app/**/icon.svg`). O efeito de verbos girando está em `web/src/components/SpinVerb.tsx`.

## Dados

`web/src/lib/seed.ts` (24 negócios sintéticos) → `web/src/lib/metrics.ts` (win rate, IC de Wilson, saúde do negócio, attention_score).
Todo número exibido é calculado ali; nada é digitado no JSX.
