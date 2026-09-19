# ADR 0006: Airbyte as the connector layer (complements the direct HubSpot client)
- Status: accepted · Date: 2026-09-19 · Decision-log row: new (D20). Related: D5 (polling), FR-ING-8 (second CRM), ADR 0005.

## Context
We want HubSpot **and other sources** without writing and maintaining a client per API. Airbyte (open source, `github.com/airbytehq/airbyte`) already ships maintained connectors and a public API.
## Decision
- Airbyte runs outside this repo (Cloud or self-managed). Its Postgres destination lands typed tables in schema `airbyte`; `omnidata airbyte ingest` maps them into silver, incrementally by `_airbyte_extracted_at` with keyset pagination on `_airbyte_raw_id`. Mapping reuses `crm/hubspot/mapping.py`, so both ingestion modes produce the same rows.
- HubSpot mapping is verified against `airbyte/source-hubspot 6.9.2` (`manifest.yaml`). Other sources go through `config/integrations.yaml` column mappings into the canonical dataset importer (ADR 0005). Shipped templates are disabled and unverified.
- `INGEST_MODE=direct` (default, D5) remains. Airbyte is read-only, so **writes and Undo stay on our HubSpot writer**.
- `AirbyteClient` covers the public API (client-credentials token, list connections, trigger sync, poll job); Airbyte's own scheduler normally drives syncs.
## Consequences
+ More sources with one mapping mechanism, maintained connectors. − A heavy dependency to operate (Kubernetes/Docker), extra DB volume, sync latency set by Airbyte's schedule, ELv2 licensing for some connectors.
Not yet exercised against a running Airbyte. We do not vendor or fork the Airbyte repository.
