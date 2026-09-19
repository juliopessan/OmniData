"""psycopg helpers. Pooler-safe: no server-side prepared statements (prepare_threshold=None)."""
from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import ROOT, get_settings

MIGRATIONS_DIR = ROOT / "supabase" / "migrations"


def connect(url: str | None = None, *, direct: bool = False) -> psycopg.Connection[dict[str, Any]]:
    s = get_settings()
    dsn = url or (s.direct_url if direct else s.database_url)
    return psycopg.connect(dsn, prepare_threshold=None, row_factory=dict_row)


def _ident(table: str) -> sql.Composed:
    return sql.SQL(".").join(sql.Identifier(p) for p in table.split("."))


def upsert(conn: psycopg.Connection[Any], table: str, rows: Sequence[dict[str, Any]], pk: Sequence[str]) -> int:
    """Idempotent INSERT ... ON CONFLICT DO UPDATE. All rows must share the same keys."""
    if not rows:
        return 0
    cols = list(rows[0].keys())
    sets = [c for c in cols if c not in pk]
    conflict = (
        sql.SQL("DO UPDATE SET ") + sql.SQL(", ").join(
            sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in sets)
        if sets else sql.SQL("DO NOTHING")
    )
    q = sql.SQL("INSERT INTO {t} ({cols}) VALUES ({vals}) ON CONFLICT ({pk}) {conflict}").format(
        t=_ident(table),
        cols=sql.SQL(", ").join(map(sql.Identifier, cols)),
        vals=sql.SQL(", ").join(sql.Placeholder() for _ in cols),
        pk=sql.SQL(", ").join(map(sql.Identifier, pk)),
        conflict=conflict,
    )
    with conn.cursor() as cur:
        cur.executemany(q, [[r[c] for c in cols] for r in rows])
    return len(rows)


@contextmanager
def advisory_lock(conn: psycopg.Connection[Any], key: int) -> Iterator[None]:
    """One run at a time per job (needs a session-level, i.e. direct, connection)."""
    with conn.cursor() as cur:
        cur.execute("select pg_try_advisory_lock(%s) as ok", (key,))
        row = cur.fetchone()
    if not row or not row["ok"]:
        raise RuntimeError(f"another run holds advisory lock {key}")
    try:
        yield
    finally:
        with conn.cursor() as cur:
            cur.execute("select pg_advisory_unlock(%s)", (key,))


def migrate(conn: psycopg.Connection[Any], directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Forward-only migrations (rule 6): each file runs once, in order, in its own transaction."""
    with conn.cursor() as cur:
        cur.execute("create table if not exists public._omnidata_migrations "
                    "(name text primary key, applied_at timestamptz not null default now())")
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("select name from public._omnidata_migrations")
        applied = {r["name"] for r in cur.fetchall()}
    done: list[str] = []
    for f in sorted(directory.glob("*.sql")):
        if f.name in applied:
            continue
        with conn.cursor() as cur:
            cur.execute(f.read_text())
            cur.execute("insert into public._omnidata_migrations (name) values (%s)", (f.name,))
        conn.commit()
        done.append(f.name)
    return done
