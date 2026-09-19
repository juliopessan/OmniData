"""`omnidata` CLI (not `od`, which collides with the POSIX command — D17)."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from .crm.hubspot.client import HubSpotClient

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
app.add_typer(serve_app, name="serve")
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
    """FR-BOT-1: create the user as 'invited' and send template onboarding_v1. Activation happens on the reply 'Aceito'."""
    import re

    from .bot.gateway import WhatsAppCloudGateway
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
    if s.whatsapp_access_token:
        async def send() -> None:
            await WhatsAppCloudGateway(s.whatsapp_phone_number_id, s.whatsapp_access_token).send_template(phone, "onboarding_v1", [name or "tudo bem"], "aceito")
        asyncio.run(send())
        typer.echo("invited + template sent")
    else:
        typer.echo("invited (WHATSAPP_ACCESS_TOKEN not set: template not sent)")


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
