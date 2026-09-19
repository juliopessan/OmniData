# OmniData

**Seu time não abre o CRM. Mas responde o WhatsApp.**

<p align="center"><img src="docs/assets/hero.png" alt="Landing do OmniData: o hero com o livro-razão calculado a partir de dados sintéticos" width="900"></p>

O OmniData leva a inteligência do HubSpot para o WhatsApp do vendedor. Quem cuida dele é o **Observatório**, uma equipe de seis assessores de IA
(Orion, Vega, Altair, Lyra, Aurora e Argus): o Orion lê o pedido e divide o trabalho, e cada especialista responde assinando a própria parte.
Número na tela vem do SQL, nunca do modelo. É a primeira fatia de uma visão 360° do cliente.

**Demo do site:** https://omnidata-web-eta.vercel.app (dados sintéticos; login e cadastro são só demonstração).

<sub>Screenshot gerado por `scripts/screenshot-hero.sh` (Chrome headless sobre o build de produção). Os números do hero são calculados de dados sintéticos.</sub>

## Estado atual

| Peça | Estado |
|---|---|
| Front-end (landing, funcionalidades, preços, login, cadastro, dashboard) | Pronto, no ar na Vercel |
| Banco, migrations, views `gold`/`serving`, backup | Pronto e testado contra Postgres real |
| Ingestão do HubSpot (backfill retomável, incremental, histórico, snapshots, `audit`) | Pronto; **testado só com fixtures e HubSpot simulado** |
| Bot no WhatsApp (webhook, fila, orquestrador, escritas com recibo/Desfazer, alertas, resumo matinal) | Pronto; **testado só com simulação** |
| Observatório (Orion planeja, especialistas executam) | Pronto; falta medir a acurácia do planejador com frases reais |
| Áudios do WhatsApp (transcrição) | Pronto; **ainda não rodou na API real da OpenAI** |
| Upload de datasets (CSV/XLSX de negócios e metas): página, API e CLI | Pronto; testado com uma exportação real do HubSpot (1000 negócios) e no navegador |
| Airbyte como camada de conectores (HubSpot + outras fontes por mapeamento) | Pronto no código; **nunca rodou contra um Airbyte real** ([docs/airbyte.md](docs/airbyte.md)) |
| Motivo de perda, previsão, coach (M2/M3), dbt | Não implementado (ADR 0002) |

Nada acima foi exercitado contra HubSpot, Meta ou LLM reais: veja **[docs/go-live.md](docs/go-live.md)** para o que depende das suas contas.

## O Observatório (harness agêntico, ADR 0003)

| Membro | Função | Ferramentas |
|---|---|---|
| **Orion** | Coordenador: analisa o pedido, monta o plano (≤ 3 passos) e devolve uma resposta só | — |
| **Vega** | Analista de Metas | `get_kpis`, `get_quota_status` |
| **Altair** | Gerente de Pipeline | `get_pipeline_summary`, `get_deal`, `list_deals_needing_action` |
| **Lyra** | Escriba do CRM (recibo + Desfazer) | `add_note`, `create_task`, `propose_deal_update`, `undo_last` |
| **Aurora** | Rotina e Alertas | `get_morning_brief` |
| **Argus** | Auditor de Confiança | `get_data_quality` |

O LLM só *propõe* o plano; o código valida (allowlist por especialista, no máximo 1 escrita e por último). Endereçamento direto: “Vega, como estou na meta?”. `uv run omnidata team` lista a equipe; `team export` gera `web/src/lib/team.json` (um teste garante a sincronia).

**Áudios do WhatsApp:** transcritos com `gpt-transcribe` (OpenAI, US$ 0,0045/min; fallback `gpt-4o-mini-transcribe`), decodificados para WAV via ffmpeg, com limite de 180 s e orçamento diário por usuário. O bot mostra “Entendi: …” antes de responder, e escritas de risco continuam pedindo confirmação. Sem Azure no projeto (ADR 0004). Para escolher o modelo com seus áudios: `scripts/bench_transcribe.py`.

## Dados de entrada

- **Upload:** `/dashboard/datasets` (arrastar-e-soltar, prévia, relatório de erros por linha) ou `uv run omnidata dataset import arquivo.csv --kind deals --apply`. Reconhece a exportação do HubSpot em pt-BR, tira ganho/perdido da etapa e o motivo de perda das notas. Detalhes em [docs/datasets.md](docs/datasets.md).
- **Airbyte:** HubSpot e outras fontes aterrissam no Postgres e o OmniData mapeia para o `silver` (`INGEST_MODE=airbyte`). O cliente próprio do HubSpot continua sendo o padrão e o único que escreve no CRM. Guia em [docs/airbyte.md](docs/airbyte.md).

## Estrutura

```
web/                      Next.js 15 + Ledger (deploy: Vercel, Root Directory = web)
src/omnidata/
  agents/                 equipe (team.py) e validação de planos (orion.py)
  bot/                    orquestrador, ações de escrita, repositórios com Principal, gateway WhatsApp, webhook
  llm/                    chat (anthropic | openai), transcrição, guarda de números
  crm/hubspot/            cliente resiliente, mapeamento, escrita
  datasets/               upload: leitura CSV/XLSX, validação, importador
  integrations/airbyte/   cliente da API, aterrissagem HubSpot, mapeamento de outras fontes
  ingest/  alerts/  api/  jobs/  security/
supabase/migrations/      SQL forward-only (bronze, silver, app, gold, serving)
docs/                     go-live.md, datasets.md, airbyte.md, templates.md, adr/ (0001–0006)
scripts/                  screenshot-hero.sh, bench_transcribe.py
```

## Rodar

**Back-end** (Python 3.12, [uv](https://docs.astral.sh/uv/), ffmpeg para áudios):

```bash
uv sync --extra dev
cp .env.example .env            # DATABASE_URL, HUBSPOT_ACCESS_TOKEN, chaves de LLM/WhatsApp (nunca commite o .env)
uv run omnidata db migrate
uv run omnidata dev seed        # CRM sintético, sem PII
uv run omnidata audit           # relatório de prontidão + go/no-go
uv run omnidata audit properties && uv run omnidata ingest backfill   # requer token do HubSpot
uv run omnidata serve api       # webhook + /healthz + /readyz
uv run omnidata serve worker    # fila de mensagens + ingestão + alertas
make check                      # ruff + mypy + pytest
```

Os testes de integração precisam de Postgres (`TEST_DATABASE_URL`); sem ele, são ignorados. Em produção: `docker compose up` (api + worker) em qualquer host de containers.

**Front-end:**

```bash
cd web && npm install && npm run dev   # http://localhost:3000
```

Deploy na Vercel: importe o repositório com **Root Directory = `web`**; framework Next.js, sem variáveis de ambiente.

## Rotas do site

| Rota | Conteúdo |
|---|---|
| `/` | Landing (Hook → Re-Hook → Meat → CTA) com livro-razão calculado de dados sintéticos |
| `/funcionalidades` | Blocos por tema com exemplos de conversa no WhatsApp |
| `/precos`, `/login`, `/cadastro` | Planos todos “Sob consulta”; login/cadastro **sem autenticação real** |
| `/dashboard/*` | Visão geral, negócios, alertas, equipe, WhatsApp, qualidade dos dados |

Cada rota tem `<title>` próprio; o favicon é a mesma marca em todas (`web/src/app/**/icon.svg`). O efeito de verbos girando está em `web/src/components/SpinVerb.tsx`.

## Dados do site

`web/src/lib/seed.ts` (24 negócios sintéticos) → `web/src/lib/metrics.ts` (win rate, IC de Wilson, saúde do negócio, attention_score).
Todo número exibido é calculado ali; nada é digitado no JSX.
