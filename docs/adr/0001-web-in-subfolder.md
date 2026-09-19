# ADR 0001: front-end lives in `web/`, Python package at `src/omnidata/`
- Status: accepted · Date: 2026-09-19 · Related: PRD §6.1 (repo layout), D4

## Context
PRD §6.1 puts the Python package at `src/omnidata/`. The SaaS front-end (Next.js) also wanted `src/`.
## Decision
Keep the PRD layout for Python; move the Next.js app to `web/` (deploy root directory = `web`).
## Consequences
Two toolchains in one repo (uv + npm). CI runs both. No change to any locked decision in §5.
