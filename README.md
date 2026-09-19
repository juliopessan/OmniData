# OmniData

Inteligência de vendas no WhatsApp, alimentada pelo HubSpot — a primeira fatia de uma visão 360° do cliente.

Este repositório contém, por ora, o **front-end SaaS** (landing, funcionalidades, preços, login, cadastro e dashboard),
em Next.js 15 + TypeScript, com o design system **Ledger**: verde-menta = medido, argila = não verificado, reservados.
O back-end do PRD (ingestão HubSpot, dbt, orquestrador WhatsApp) ainda não foi implementado.

## Rodar

```bash
npm install
npm run dev     # http://localhost:3000
npm run build && npm run typecheck
```

## Rotas

| Rota | Conteúdo |
|---|---|
| `/` | Landing com livro-razão calculado a partir de dados sintéticos |
| `/funcionalidades` | Blocos por tema com exemplos de conversa no WhatsApp (filtro por tema) |
| `/precos`, `/login`, `/cadastro` | Preços ilustrativos; login/cadastro **sem autenticação real** |
| `/dashboard/*` | Visão geral, negócios, alertas, WhatsApp, qualidade dos dados |

Cada rota tem `<title>` e favicon próprios (`src/app/**/icon.svg`). O efeito de verbos girando está em `src/components/SpinVerb.tsx`.

## Dados

`src/lib/seed.ts` (24 negócios sintéticos) → `src/lib/metrics.ts` (win rate, IC de Wilson, saúde do negócio, attention_score).
Todo número exibido é calculado ali; nada é digitado no JSX.
