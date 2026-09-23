"""`omnidata` CLI (not `od`, which collides with the POSIX command — D17)."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from .bot.evolution import EvolutionAdminClient
    from .config import Settings
    from .crm.hubspot.client import HubSpotClient
    from .integrations.airbyte.client import AirbyteClient

from .config import ROOT, get_settings

app = typer.Typer(no_args_is_help=True, help="OmniData — sales intelligence on HubSpot + WhatsApp")
ingest_app = typer.Typer(no_args_is_help=True, help="Ingestion jobs")
audit_app = typer.Typer(help="Readiness audit", invoke_without_command=True)
dev_app = typer.Typer(no_args_is_help=True)
db_app = typer.Typer(no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")
app.add_typer(audit_app, name="audit")
app.add_typer(dev_app, name="dev")
user_app = typer.Typer(no_args_is_help=True, help="Users (WhatsApp onboarding, LGPD)")
quota_app = typer.Typer(no_args_is_help=True)
serve_app = typer.Typer(no_args_is_help=True, help="Run services")
app.add_typer(db_app, name="db")
app.add_typer(user_app, name="user")
app.add_typer(quota_app, name="quota")
dataset_app = typer.Typer(no_args_is_help=True, help="Dataset uploads (CSV/XLSX -> silver)")
app.add_typer(serve_app, name="serve")
airbyte_app = typer.Typer(no_args_is_help=True, help="Airbyte connector layer (docs/airbyte.md)")
app.add_typer(dataset_app, name="dataset")
insights_app = typer.Typer(no_args_is_help=True, help="Company insights (dores, termos, ERPs, demanda)")
app.add_typer(airbyte_app, name="airbyte")
hygiene_app = typer.Typer(no_args_is_help=True, help="Data hygiene: the Coach's fix queue")
app.add_typer(insights_app, name="insights")
eval_app = typer.Typer(no_args_is_help=True, help="Evaluations (no database needed)")
forecast_app = typer.Typer(no_args_is_help=True, help="Statistical forecast of the open pipeline")
evolution_app = typer.Typer(no_args_is_help=True, help="Evolution API: create/connect/inspect the WhatsApp instance (ADR 0008)")
app.add_typer(hygiene_app, name="hygiene")
app.add_typer(forecast_app, name="forecast")
app.add_typer(eval_app, name="eval")
app.add_typer(evolution_app, name="evolution")


def _evolution_admin() -> tuple[Settings, EvolutionAdminClient]:
    """Common guard + client for every evolution_app command; returns (Settings, EvolutionAdminClient)."""
    from .bot.evolution import EvolutionAdminClient
    s = get_settings()
    if not (s.evolution_api_url and s.evolution_api_key):
        typer.echo("set EVOLUTION_API_URL and EVOLUTION_API_KEY first (.env)", err=True)
        raise typer.Exit(2)
    return s, EvolutionAdminClient(s.evolution_api_url, s.evolution_api_key)


@evolution_app.command("create-instance")
def evolution_create_instance(
    name: str = typer.Option(..., help="instance name, e.g. omnidata"),
    number: str = typer.Option("", help="E.164 WhatsApp number for this instance (optional; Evolution can ask on scan instead)"),
    webhook_url: str = typer.Option("", help="e.g. https://your-api-host/webhooks/evolution (needs EVOLUTION_WEBHOOK_SECRET set)"),
    save_qr: Path = typer.Option(Path("evolution-qrcode.png"), help="where to save the QR code, if the response includes one"),
) -> None:
    """Step 1 of the pipeline (ADR 0008): create the instance. If it isn't already connected, saves a QR code —
    open it and scan with WhatsApp on the phone/number that will run the bot (Settings > Linked Devices > Link a Device)."""
    import base64

    s, c = _evolution_admin()
    if webhook_url and not s.evolution_webhook_secret:
        typer.echo("EVOLUTION_WEBHOOK_SECRET is not set: the webhook would accept unauthenticated calls. Set it first.", err=True)
        raise typer.Exit(2)

    async def go() -> None:
        try:
            res = await c.create_instance(name, number=number or None, webhook_url=webhook_url or None,
                                          webhook_secret=s.evolution_webhook_secret or None)
            qr = (res.get("qrcode") or {}).get("base64")
            if isinstance(qr, str) and qr:
                save_qr.write_bytes(base64.b64decode(qr.split(",", 1)[-1]))
                typer.echo(f"instance '{name}' created. QR code saved to {save_qr} — scan it with WhatsApp before it expires.")
            else:
                typer.echo(f"instance '{name}' created. No QR in the response — run `omnidata evolution qrcode --name {name}`.")
        finally:
            await c.aclose()
    asyncio.run(go())
    typer.echo(f"Once connected (`omnidata evolution status --name {name}` shows open), set EVOLUTION_INSTANCE={name} in your .env.")


@evolution_app.command("qrcode")
def evolution_qrcode(name: str = typer.Option(..., help="instance name"),
                     save_qr: Path = typer.Option(Path("evolution-qrcode.png"))) -> None:
    """Step 2: (re-)issue a QR code for an instance that isn't connected yet."""
    import base64

    _, c = _evolution_admin()

    async def go() -> None:
        try:
            res = await c.qrcode(name)
            b64 = res.get("base64")
            if not isinstance(b64, str) or not b64:
                typer.echo("no QR code in the response (the instance may already be connected — check `evolution status`)", err=True)
                raise typer.Exit(1)
            save_qr.write_bytes(base64.b64decode(b64.split(",", 1)[-1]))
            typer.echo(f"QR code saved to {save_qr} — scan it with WhatsApp before it expires.")
        finally:
            await c.aclose()
    asyncio.run(go())


@evolution_app.command("status")
def evolution_status(name: str = typer.Option(..., help="instance name")) -> None:
    """Step 3: poll until this prints 'open' (connected). 'connecting' right after a scan is normal for a few seconds."""
    _, c = _evolution_admin()

    async def go() -> None:
        try:
            typer.echo(await c.connection_state(name))
        finally:
            await c.aclose()
    asyncio.run(go())


@evolution_app.command("set-webhook")
def evolution_set_webhook(name: str = typer.Option(..., help="instance name"),
                          url: str = typer.Option(..., help="e.g. https://your-api-host/webhooks/evolution")) -> None:
    """Reconfigure the webhook on an already-created instance (e.g. after moving where the API is hosted)."""
    s, c = _evolution_admin()
    if not s.evolution_webhook_secret:
        typer.echo("EVOLUTION_WEBHOOK_SECRET is not set: the webhook would accept unauthenticated calls. Set it first.", err=True)
        raise typer.Exit(2)

    async def go() -> None:
        try:
            await c.set_webhook(name, url, s.evolution_webhook_secret)
            typer.echo("webhook set")
        finally:
            await c.aclose()
    asyncio.run(go())


@evolution_app.command("list-instances")
def evolution_list_instances() -> None:
    _, c = _evolution_admin()

    async def go() -> None:
        try:
            for i in await c.fetch_instances():
                typer.echo(i)
        finally:
            await c.aclose()
    asyncio.run(go())


@evolution_app.command("delete-instance")
def evolution_delete_instance(name: str = typer.Option(..., help="instance name"),
                              yes: bool = typer.Option(False, "--yes", help="skip the confirmation prompt")) -> None:
    if not yes:
        typer.confirm(f"Delete Evolution instance '{name}'? This disconnects the WhatsApp number.", abort=True)
    _, c = _evolution_admin()

    async def go() -> None:
        try:
            await c.delete_instance(name)
            typer.echo(f"instance '{name}' deleted")
        finally:
            await c.aclose()
    asyncio.run(go())


@dataset_app.command("import")
def dataset_import(file: Path, kind: str = typer.Option("deals", help="deals | quotas"),
                   apply: bool = typer.Option(False, "--apply", help="write to the database (default: validate only)"),
                   allow_partial: bool = typer.Option(False, help="import valid rows even if some rows have errors"),
                   replace: bool = typer.Option(False, help="deals: first delete everything imported before (ids starting with up:)"),
                   no_notes: bool = typer.Option(False, help="deals: do not import note text"),
                   stage_order: str = typer.Option("", help="comma-separated open stages, first to last (default: guessed from names)")) -> None:
    """Validate (and with --apply, import) a CSV/XLSX. Exit code 2 when the file is rejected."""
    import json

    from .datasets.importer import ImportOptions, import_file
    from .datasets.parse import UploadError
    from .datasets.spec import KINDS
    from .db import connect
    if kind not in KINDS:
        typer.echo(f"unknown kind: {kind}", err=True)
        raise typer.Exit(2)
    s = get_settings()
    opts = ImportOptions(dry_run=not apply, allow_partial=allow_partial, replace=replace, import_notes=not no_notes,
                         stage_order=[x.strip() for x in stage_order.split(",") if x.strip()] or None, uploaded_by="cli")
    try:
        with connect() as conn:
            res = import_file(conn, kind, file.read_bytes(), file.name, opts, max_bytes=s.dataset_max_bytes, max_rows=s.dataset_max_rows)
    except UploadError as exc:
        typer.echo(f"rejected: {exc.message}", err=True)
        raise typer.Exit(2) from exc
    d = res.to_dict()
    rep = d["report"]
    typer.echo(json.dumps({k: rep[k] for k in ("total_rows", "valid_rows", "error_count", "mapping", "ignored_columns", "unstored_columns",
                                              "missing_required", "warnings", "stage_order", "summary")}, ensure_ascii=False, indent=2, default=str))
    for e in rep["errors"][:20]:
        typer.echo(f"  linha {e['line']} · {e['column']}: {e['message']}", err=True)
    typer.echo(f"status: {res.status}" + (f" · imported: {res.imported}" if res.imported else "") + ("" if apply else "  (dry run: use --apply to write)"))
    if res.status in ("rejected", "failed") or (not apply and not rep["ok"]):
        raise typer.Exit(2)


@dataset_app.command("template")
def dataset_template(kind: str = "deals") -> None:
    """Print a CSV template."""
    from .datasets.templates import TEMPLATES
    typer.echo(TEMPLATES[kind], nl=False)


@dataset_app.command("spec")
def dataset_spec() -> None:
    """JSON spec shared with the web UI: `omnidata dataset spec > web/src/lib/dataset-spec.json`."""
    import json

    from .datasets.spec import spec_json
    typer.echo(json.dumps(spec_json(), ensure_ascii=False, indent=2))


def _airbyte_client() -> AirbyteClient:
    from .integrations.airbyte.client import AirbyteClient
    s = get_settings()
    if not (s.airbyte_url and s.airbyte_client_id and s.airbyte_client_secret):
        typer.echo("set AIRBYTE_URL, AIRBYTE_CLIENT_ID and AIRBYTE_CLIENT_SECRET (see .env.example)", err=True)
        raise typer.Exit(2)
    return AirbyteClient(s.airbyte_url, s.airbyte_client_id, s.airbyte_client_secret)


@airbyte_app.command("connections")
def airbyte_connections() -> None:
    """List connections from the Airbyte API (find the ids to put in config/integrations.yaml)."""
    async def run() -> None:
        c = _airbyte_client()
        try:
            for x in await c.list_connections():
                typer.echo(f"{x.get('connectionId')}  {x.get('name')}  status={x.get('status')}")
        finally:
            await c.aclose()
    asyncio.run(run())


@airbyte_app.command("sync")
def airbyte_sync(connection_id: list[str] = typer.Option([], "--connection-id", help="default: all in config/integrations.yaml"),
                 wait: bool = typer.Option(True, help="wait until the job ends")) -> None:
    """Trigger Airbyte syncs (Airbyte's own scheduler normally does this)."""
    from .integrations.airbyte.generic import load_config
    ids = connection_id or [c["id"] for c in (load_config().get("airbyte", {}).get("connections") or [])]
    if not ids:
        typer.echo("no connection ids: pass --connection-id or fill airbyte.connections", err=True)
        raise typer.Exit(2)

    async def run() -> bool:
        c = _airbyte_client()
        ok = True
        try:
            for cid in ids:
                job = await c.trigger_sync(cid)
                typer.echo(f"job {job.id} started ({cid})")
                if wait:
                    job = await c.wait(job.id)
                    typer.echo(f"job {job.id}: {job.status}" + (f" rows={job.rows_synced}" if job.rows_synced is not None else ""))
                    ok = ok and job.ok
        finally:
            await c.aclose()
        return ok
    if not asyncio.run(run()):
        raise typer.Exit(1)


@airbyte_app.command("ingest")
def airbyte_ingest(full: bool = typer.Option(False, help="ignore cursors and re-read everything"),
                   stream: list[str] = typer.Option([], "--stream", help="limit to these streams")) -> None:
    """Map the HubSpot tables Airbyte landed into silver (incremental by _airbyte_extracted_at)."""
    from .db import advisory_lock, connect
    from .integrations.airbyte.landing import ingest
    with connect(direct=True) as conn, advisory_lock(conn, 7006):
        for k, v in ingest(conn, get_settings().airbyte_schema, streams=stream or None, full=full).items():
            typer.echo(f"{k:26s} {v}")


@airbyte_app.command("generic")
def airbyte_generic(apply: bool = typer.Option(False, "--apply"), name: str = typer.Option("", help="only this mapping (also runs it if disabled)")) -> None:
    """Import other Airbyte sources through the canonical dataset importer (config/integrations.yaml `generic`)."""
    from .db import connect
    from .integrations.airbyte.generic import run_all
    with connect() as conn:
        for k, v in run_all(conn, apply=apply, only=name or None, max_rows=get_settings().dataset_max_rows).items():
            typer.echo(f"{k:14s} {v}")
    if not apply:
        typer.echo("(dry run: use --apply to write)")


@insights_app.command("spec")
def insights_spec() -> None:
    """JSON shared with the web UI: `omnidata insights spec > web/src/lib/insights-spec.json`."""
    import json

    from .insights.spec import spec_json
    typer.echo(json.dumps(spec_json(), ensure_ascii=False, indent=2))


@insights_app.command("analyze")
def insights_analyze(file: Path, limit: int = 8) -> None:
    """Run the insights engine on a deals CSV/XLSX (no database needed)."""
    import json

    from .datasets.parse import read_table
    from .datasets.spec import DEALS
    from .datasets.validate import validate
    from .insights.compute import Rec, analyze
    data = file.read_bytes()
    rep, rows = validate(DEALS, read_table(data, file.name), file.name, data)
    if not rows:
        typer.echo("no valid deals in the file", err=True)
        raise typer.Exit(2)
    recs = [Rec(r["id"], r["name"], r["status"], r["amount"], r["campaign"], r["lost_reason"], r["notes"]) for r in rows]
    typer.echo(json.dumps(analyze(recs, limit), ensure_ascii=False, indent=2, default=str))


@eval_app.command("planner")
def eval_planner(mode: str = typer.Option("keyword", help="keyword (no LLM) | llm (uses LLM_PROVIDER and its key)"),
                 cases: Path | None = typer.Option(None, help="YAML file with cases (default: the golden set)"),
                 as_json: bool = typer.Option(False, "--json", help="machine-readable output"),
                 min_correct: float = typer.Option(0.0, help="exit 1 if the share of correct cases is below this")) -> None:
    """Does Orion send each request to the right specialist and tool? Exit 1 on any critical case or if below --min-correct."""
    import json
    import logging

    from .evals import planner as ev
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request would bury the report
    cs = ev.load_cases(cases) if cases else ev.load_cases()
    if mode == "keyword":
        rep = ev.run_keyword(cs)
    elif mode == "llm":
        from .jobs.worker import build_llm
        llm = build_llm(get_settings())
        if llm is None:
            typer.echo("no LLM configured: set LLM_PROVIDER and its key (ANTHROPIC_API_KEY, or OPENAI_API_KEY + models) in .env", err=True)
            raise typer.Exit(2)
        rep = asyncio.run(ev.run_llm(cs, llm))
    else:
        typer.echo("mode must be keyword or llm", err=True)
        raise typer.Exit(2)
    typer.echo(json.dumps(rep.to_json(), ensure_ascii=False, indent=2) if as_json else ev.format_report(rep))
    if rep.count("critical") or rep.rate("correct") < min_correct:
        raise typer.Exit(1)


@forecast_app.command("analyze")
def forecast_analyze(file: Path, quota: float | None = typer.Option(None, help="target for the period, in R$"),
                     realized: float = typer.Option(0.0, help="already won in the period, in R$")) -> None:
    """Forecast for a deals CSV/XLSX (no database needed): what the open pipeline can still add and the chance of reaching --quota."""
    import json

    from .datasets.parse import read_table
    from .datasets.spec import DEALS
    from .datasets.validate import validate
    from .forecast.compute import forecast
    data = file.read_bytes()
    _, rows = validate(DEALS, read_table(data, file.name), file.name, data)
    if not rows:
        typer.echo("no valid deals in the file", err=True)
        raise typer.Exit(2)
    wins, losses = sum(1 for r in rows if r["status"] == "won"), sum(1 for r in rows if r["status"] == "lost")
    open_amounts = [float(r["amount"] or 0) for r in rows if r["status"] == "open"]
    typer.echo(json.dumps(forecast(open_amounts, wins, losses, realized, quota, has_created_at=any(r["created_at"] for r in rows)), ensure_ascii=False, indent=2, default=str))


@hygiene_app.command("spec")
def hygiene_spec() -> None:
    """JSON shared with the web UI: `omnidata hygiene spec > web/src/lib/hygiene-spec.json`."""
    import json

    from .hygiene.spec import spec_json
    typer.echo(json.dumps(spec_json(), ensure_ascii=False, indent=2))


@hygiene_app.command("analyze")
def hygiene_analyze(file: Path, limit: int = 8, manager: bool = typer.Option(True, help="include owner-level items")) -> None:
    """Fix queue for a deals CSV/XLSX (no database needed)."""
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from .datasets.parse import read_table
    from .datasets.spec import DEALS
    from .datasets.validate import validate
    from .hygiene.compute import Deal, fix_queue
    data = file.read_bytes()
    rep, rows = validate(DEALS, read_table(data, file.name), file.name, data)
    deals = [Deal(r["id"], r["name"], r["amount"], r["owner"], "deactivated" not in (r["owner"] or "").lower(), r["close_date"], r["next_activity"], len(r["notes"]))
             for r in rows if r["status"] == "open"]
    today = datetime.now(ZoneInfo(get_settings().app_timezone)).date()
    typer.echo(json.dumps(fix_queue(deals, today, is_manager=manager, limit=limit), ensure_ascii=False, indent=2, default=str))


@app.command("team")
def team_cmd(action: str = typer.Argument("list", help="list | export")) -> None:
    """The Observatório: who does what. `export` prints JSON for the web UI."""
    import json

    from .agents.team import TEAM, TEAM_NAME, export
    if action == "export":
        typer.echo(json.dumps(export(), ensure_ascii=False, indent=2))
        return
    typer.echo(TEAM_NAME)
    for a in TEAM.values():
        typer.echo(f"  {a.name:<7} {a.title:<24} tools: {', '.join(a.tools) or '— (planeja e coordena)'}")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


def _client() -> HubSpotClient:
    from .crm.hubspot.client import HubSpotClient
    s = get_settings()
    if not s.hubspot_access_token:
        typer.echo("HUBSPOT_ACCESS_TOKEN is not set (see .env.example)", err=True)
        raise typer.Exit(2)
    return HubSpotClient(s.hubspot_access_token, rps=s.hubspot_rps, search_rps=s.hubspot_search_rps)


@db_app.command("migrate")
def db_migrate() -> None:
    from .db import connect, migrate
    with connect(direct=True) as conn:
        done = migrate(conn)
    typer.echo(f"applied: {', '.join(done) or 'nothing (up to date)'}")


@db_app.command("backup")
def db_backup(out: Path = typer.Option(ROOT / "backups", help="Output directory")) -> None:
    from .ingest.backup import backup
    typer.echo(str(backup(get_settings().direct_url, out)))


@db_app.command("size-report")
def db_size_report() -> None:
    import json

    from .db import connect
    from .ingest.backup import size_report
    with connect() as conn:
        typer.echo(json.dumps(size_report(conn), indent=2))


@dev_app.command("seed")
def dev_seed(deals: int = 2000) -> None:
    from .db import connect
    from .ingest.seed import seed
    with connect() as conn:
        typer.echo(str(seed(conn, deals)))


@ingest_app.command("backfill")
def ingest_backfill(months: int = typer.Option(24, help="How far back to load")) -> None:
    from .db import advisory_lock, connect
    from .ingest.jobs import backfill

    async def run() -> dict[str, int]:
        client = _client()
        since = datetime.now(UTC).replace(microsecond=0) - timedelta(days=30 * months)
        try:
            with connect(direct=True) as conn, advisory_lock(conn, 7001):
                return await backfill(conn, client, since)
        finally:
            await client.aclose()
    typer.echo(str(asyncio.run(run())))


@ingest_app.command("incremental")
def ingest_incremental() -> None:
    from .db import advisory_lock, connect
    from .ingest.jobs import incremental

    async def run() -> dict[str, int]:
        client = _client()
        try:
            with connect(direct=True) as conn, advisory_lock(conn, 7002):
                return await incremental(conn, client)
        finally:
            await client.aclose()
    typer.echo(str(asyncio.run(run())))


@ingest_app.command("snapshot")
def ingest_snapshot() -> None:
    from .db import connect
    from .ingest.jobs import weekly_snapshot
    with connect() as conn:
        typer.echo(f"snapshot rows: {weekly_snapshot(conn)}")


@audit_app.callback()
def audit(ctx: typer.Context, out: Path = typer.Option(ROOT / "reports", help="Report directory")) -> None:
    """Data-readiness report (markdown + JSON) with go/no-go per use case."""
    if ctx.invoked_subcommand:
        return
    from .db import connect
    from .ingest.audit import readiness, readiness_json, render_readiness_md
    with connect() as conn:
        r = readiness(conn)
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit.md").write_text(render_readiness_md(r))
    (out / "audit.json").write_text(readiness_json(r))
    typer.echo(render_readiness_md(r))


@audit_app.command("properties")
def audit_props(out: Path = typer.Option(ROOT / "reports")) -> None:
    """List real property names/types for every property this PRD uses; flag missing ones."""
    from .ingest.audit import audit_properties, render_properties_md

    async def run() -> str:
        import json
        client = _client()
        try:
            report = await audit_properties(client)
        finally:
            await client.aclose()
        out.mkdir(parents=True, exist_ok=True)
        (out / "properties.json").write_text(json.dumps(report, indent=2))
        return render_properties_md(report)
    md = asyncio.run(run())
    (out / "properties.md").write_text(md)
    typer.echo(md)


@serve_app.command("api")
def serve_api(host: str = "0.0.0.0", port: int = 8000) -> None:  # noqa: S104
    import uvicorn
    uvicorn.run("omnidata.api.app:app_factory", factory=True, host=host, port=port)


@serve_app.command("worker")
def serve_worker() -> None:
    from .jobs.worker import run
    asyncio.run(run())


@user_app.command("invite")
def user_invite(phone: str = typer.Option(..., help="E.164, e.g. +5511999999999"), owner: str = typer.Option(..., help="HubSpot owner id"),
                role: str = "rep", name: str = "", manager: str = typer.Option("", help="manager phone (E.164)")) -> None:
    """FR-BOT-1: create the user as 'invited' and send the onboarding text. Activation happens on the reply 'Aceito'."""
    import re

    from .bot import strings_ptbr as S
    from .bot.evolution import EvolutionGateway
    from .db import connect
    if not re.fullmatch(r"\+\d{10,15}", phone) or role not in ("rep", "manager", "admin"):
        typer.echo("invalid phone (E.164) or role", err=True)
        raise typer.Exit(2)
    with connect() as conn, conn.cursor() as cur:
        mid = None
        if manager:
            cur.execute("select id from app.app_user where phone_e164=%s", (manager,))
            m = cur.fetchone()
            mid = m["id"] if m else None
        cur.execute("insert into app.app_user (hs_owner_id, phone_e164, display_name, role, manager_user_id) values (%s,%s,%s,%s,%s) "
                    "on conflict (phone_e164) do update set display_name=excluded.display_name returning id", (owner, phone, name or None, role, mid))
        conn.commit()
    s = get_settings()
    if s.evolution_api_key and s.evolution_instance:
        async def send() -> None:
            gw = EvolutionGateway(s.evolution_api_url, s.evolution_api_key, s.evolution_instance)
            try:
                await gw.send_text(phone, S.ONBOARDING_ASK.format(name=name or ""))
            finally:
                await gw.aclose()
        asyncio.run(send())
        typer.echo("invited + onboarding text sent")
    else:
        typer.echo("invited (EVOLUTION_API_KEY/EVOLUTION_INSTANCE not set: onboarding text not sent)")


@user_app.command("erase")
def user_erase(phone: str) -> None:
    """LGPD (US-15): remove the user and everything tied to them."""
    from .db import connect
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select id from app.app_user where phone_e164=%s", (phone,))
        u = cur.fetchone()
        if not u:
            typer.echo("user not found", err=True)
            raise typer.Exit(1)
        uid = u["id"]
        for t in ("app.wa_message", "app.conversation_state", "app.pending_action", "app.alert_event", "app.loss_reason", "app.llm_call", "app.audit_log"):
            cur.execute(f"delete from {t} where user_id = %s", (uid,))
        cur.execute("update app.app_user set manager_user_id = null where manager_user_id = %s", (uid,))
        cur.execute("delete from app.app_user where id = %s", (uid,))
        conn.commit()
    typer.echo("erased")


@quota_app.command("import")
def quota_import(csv_path: Path) -> None:
    """FR-ING-7: CSV columns owner,period_start,period_end,amount (validated before anything is written)."""
    import csv
    from datetime import date
    from decimal import Decimal, InvalidOperation

    from .db import connect, upsert
    rows, errors = [], []
    with csv_path.open() as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            try:
                ps, pe = date.fromisoformat(r["period_start"]), date.fromisoformat(r["period_end"])
                amt = Decimal(r["amount"])
                if pe < ps or amt < 0 or not r["owner"].strip():
                    raise ValueError
                rows.append({"hs_owner_id": r["owner"].strip(), "period_start": ps, "period_end": pe, "amount": amt, "source": "csv"})
            except (KeyError, ValueError, InvalidOperation):
                errors.append(f"line {i}")
    if errors:
        typer.echo("invalid rows: " + ", ".join(errors), err=True)
        raise typer.Exit(2)
    with connect() as conn:
        upsert(conn, "silver.quota", rows, ["hs_owner_id", "period_start", "period_end"])
        conn.commit()
    typer.echo(f"imported {len(rows)} quota rows")


if __name__ == "__main__":
    app()
