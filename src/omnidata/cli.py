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
app.add_typer(db_app, name="db")
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


if __name__ == "__main__":
    app()
