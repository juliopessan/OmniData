# Deploy on a VPS that already runs Traefik (e.g. Hostinger's app marketplace)

This is the recipe actually used in production (2026-09-23), on a Hostinger VPS that already had Traefik and a
shared Postgres running for other apps (Evolution API, n8n, WAHA). It reuses both instead of standing up new ones —
adjust if your host is bare.

## 1. Prerequisites already on the host
- Docker + Docker Compose.
- Traefik, with the Docker provider and a `websecure` (443, TLS via `letsencrypt`) entrypoint. Check with
  `docker inspect <a-running-app-container> --format '{{json .Config.Labels}}'` — if it already has
  `traefik.http.routers.*` labels and is reachable over HTTPS, you have this.
- A Postgres instance you can create a database in (its own container is fine). Find its compose project name with
  `docker ps` (the network is `<project>_default`) and its actual superuser name with
  `docker exec <container> env | grep POSTGRES_USER` — images that template `POSTGRES_USER` rarely use literally
  `postgres`.
- A hostname that resolves to the VPS. Hostinger VPS instances get a wildcard `*.<server>.hstgr.cloud` for free — any
  subdomain under it works with zero DNS setup. Otherwise, point an A/AAAA record at the VPS yourself.

## 2. Database
Create a dedicated role and database (never reuse another app's role). **Do not** pipe a heredoc into `docker exec`
without `-i` — it silently receives nothing and every statement in it is skipped without an error, which is how the
password ended up unset twice during the real deploy. Also avoid psql's `:'var'` substitution inside a `DO $$ ... $$`
block — it is not expanded there; interpolate the (locally generated, punctuation-free) password directly into the
SQL string instead:

```bash
DB_PASS=$(openssl rand -hex 24)
docker exec -i -u postgres <postgres-container> psql -U <its-superuser> -d postgres -v ON_ERROR_STOP=1 \
  -c "CREATE ROLE omnidata WITH LOGIN PASSWORD '${DB_PASS}'" \
  -c "CREATE DATABASE omnidata OWNER omnidata"
```

## 3. Clone and build
```bash
git clone https://github.com/juliopessan/OmniData.git app
cd app
```
Write `.env` (chmod 600, never in the repo) with `DATABASE_URL`/`DATABASE_URL_DIRECT` pointing at the container name
on its own network (e.g. `postgresql://omnidata:${DB_PASS}@<postgres-container>:5432/omnidata`), plus the usual
`LLM_PROVIDER`/`EVOLUTION_*`/`ADMIN_API_TOKEN`/`CORS_ORIGINS` from `.env.example`. Then, one directory up (so
`build: .` in `docker-compose.yml` resolves to `app/`):
```bash
API_DOMAIN=omnidata-api.example.com POSTGRES_NETWORK=<postgres-project>_default \
  docker compose -f app/docker-compose.yml -f app/docker-compose.traefik.yml --env-file app/.env build
docker compose -f app/docker-compose.yml -f app/docker-compose.traefik.yml --env-file app/.env run --rm api omnidata db migrate
docker compose -f app/docker-compose.yml -f app/docker-compose.traefik.yml --env-file app/.env up -d
```
`docker-compose.traefik.yml` (repo root) adds the Traefik labels and attaches `api`/`worker` to the existing Postgres
network, without changing the plain `docker-compose.yml` other hosts use.

## 4. Point Evolution's webhook at it
```bash
omnidata evolution set-webhook --name <instance> --url https://<API_DOMAIN>/webhooks/evolution
```
(needs `EVOLUTION_WEBHOOK_SECRET` set in the environment you run this from, same value as in the deployed `.env`).

## 5. Verify
```bash
curl https://<API_DOMAIN>/healthz   # {"status":"ok"}
curl https://<API_DOMAIN>/readyz    # {"db":"ok",...}
```
Then send one real WhatsApp message to the connected number and confirm `app.wa_message`/`app.agent_step` show it
processed with no error — the same check ADR 0008 describes.

## What this does NOT set up
No managed Postgres backup (the container's a single local volume). No log shipping. `CORS_ORIGINS` should list your
real web origin, not `*`. Rotate `ADMIN_API_TOKEN` and `EVOLUTION_WEBHOOK_SECRET` if either is ever pasted in chat or
a log.
