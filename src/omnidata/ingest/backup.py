"""Nightly backup of the irreplaceable tables (deal_snapshot, deal_property_change, app.*) and size report."""
from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

IRREPLACEABLE = ["silver.deal_snapshot", "silver.deal_property_change", "app.*"]


def pg_dump_cmd(dsn: str, out: Path, tables: list[str] | None = None) -> list[str]:
    cmd = ["pg_dump", "--format=custom", "--no-owner", f"--file={out}", dsn]
    for t in tables or IRREPLACEABLE:
        cmd.insert(-1, "--schema=app" if t == "app.*" else f"--table={t}")
    return cmd


def backup(dsn: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"omnidata-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.dump"
    subprocess.run(pg_dump_cmd(dsn, out), check=True)
    return out


def size_report(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    """Keep the DB under ~500 MB on the free tier (D3)."""
    with conn.cursor() as cur:
        cur.execute("select pg_database_size(current_database()) as b")
        total = cur.fetchone()["b"]  # type: ignore[index]
        cur.execute("""select schemaname || '.' || relname as t, pg_total_relation_size(relid) as b
                       from pg_stat_user_tables where schemaname in ('bronze','silver','gold','app')
                       order by b desc limit 10""")
        top = [{"table": r["t"], "mb": round(r["b"] / 1e6, 2)} for r in cur.fetchall()]
    return {"total_mb": round(total / 1e6, 1), "limit_mb": 500, "top_tables": top}
