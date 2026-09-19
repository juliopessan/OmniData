# ADR 0005: dataset upload through one canonical importer
- Status: accepted · Date: 2026-09-19 · Decision-log row: new (D19). Related: FR-ING-7, D2, D14.

## Context
Pilots without HubSpot access, historical backfills and quota files arrive as CSV/XLSX. The only entry today is `omnidata quota import`.
## Decision
One module (`datasets/`): parse (CSV utf-8/cp1252, `, ; tab |`, XLSX) → map headers by accent-insensitive aliases → validate every row with line/column errors → import into silver in one transaction, idempotently.
Kinds: `deals` (built from a real pt-BR HubSpot export: won/lost from the stage name, loss reason from note text, owner by name) and `quotas`.
Uploaded ids are prefixed (`up:`) so they never collide with HubSpot ids. The file itself is not stored (D14): only SHA-256 and stats in `app.dataset_upload`.
Entry points: CLI, `POST /api/datasets/{kind}` (bearer `ADMIN_API_TOKEN`, dry run by default) and the dashboard page.
## Consequences
Uploads and direct HubSpot ingestion can describe the same deals twice; the docs say to pick one path. Exports without creation dates cannot feed stall/cycle metrics. Upload auth is a static token until real login exists (D-auth is open); rate limiting is missing.
The same importer is reused by Airbyte-landed tables from other sources (ADR 0006), so every source gets identical validation.
