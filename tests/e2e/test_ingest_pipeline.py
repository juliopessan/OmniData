"""Ingestion against a fake HubSpot + real Postgres: FR-ING-1..4 acceptance criteria."""
from datetime import UTC, datetime, timedelta

import pytest

from omnidata.crm.hubspot.client import HubSpotClient, HubSpotError
from omnidata.db import advisory_lock
from omnidata.ingest import jobs
from omnidata.ingest.audit import readiness

from ..fakehub import T0, FakeHubSpot

NOW = T0 + timedelta(days=30)
OBJECTS = ["deals"]


async def nosleep(_): ...


def hub_client(fake):
    return HubSpotClient("t", transport=fake.transport(), sleep=nosleep, max_retries=0)


def count(conn, table):
    with conn.cursor() as cur:
        cur.execute(f"select count(*) as n from {table}")
        return cur.fetchone()["n"]


async def test_backfill_row_parity_and_idempotent(conn):  # FR-ING-1
    fake = FakeHubSpot(deals=9)
    c = hub_client(fake)
    await jobs.backfill(conn, c, T0, now=NOW, objects=OBJECTS)
    assert count(conn, "silver.deal") == 9 == count(conn, "bronze.hubspot_raw")
    assert count(conn, "silver.deal_stage_history") == 18  # 2 stages each
    before = {t: count(conn, t) for t in ("silver.deal", "silver.deal_stage_history", "silver.deal_property_change",
                                          "silver.deal_contact")}
    with conn.cursor() as cur:  # force a full re-run
        cur.execute("update app.ingest_window set status='pending'")
    conn.commit()
    await jobs.backfill(conn, c, T0, now=NOW, objects=OBJECTS)
    assert {t: count(conn, t) for t in before} == before  # no duplicates


async def test_won_lost_and_close_date_pushes_persisted(conn):  # FR-ING-1/2
    await jobs.backfill(conn, hub_client(FakeHubSpot(deals=6)), T0, now=NOW, objects=OBJECTS)
    with conn.cursor() as cur:
        cur.execute("select count(*) filter (where is_won) w, count(*) filter (where is_lost) l, "
                    "count(*) filter (where is_open) o, min(close_date_pushes) p from silver.deal")
        r = cur.fetchone()
    assert (r["w"], r["l"], r["o"], r["p"]) == (2, 2, 2, 1)


async def test_backfill_resumes_without_refetching_completed_windows(conn):  # FR-ING-3
    fake = FakeHubSpot(deals=9)
    # 30 days / 10-day windows = 3 windows. Each window = 2 search calls (probe + page). Fail on the 3rd window.
    fake.fail_after = 4
    with pytest.raises(HubSpotError):
        await jobs.backfill(conn, hub_client(fake), T0, now=NOW, window_days=10, objects=OBJECTS)
    with conn.cursor() as cur:
        cur.execute("select status, count(*) n from app.ingest_window group by 1")
        st = {r["status"]: r["n"] for r in cur.fetchall()}
    assert st == {"done": 2, "failed": 1}
    fake.fail_after, fake.search_calls = None, 0
    await jobs.backfill(conn, hub_client(fake), T0, now=NOW, window_days=10, objects=OBJECTS)
    assert fake.search_calls == 2  # only the failed window was searched again
    assert count(conn, "silver.deal") == 9


async def test_incremental_picks_up_edits_within_one_cycle(conn):  # FR-ING-1 AC
    fake = FakeHubSpot(deals=3)
    c = hub_client(fake)
    await jobs.backfill(conn, c, T0, now=NOW, objects=OBJECTS)
    edited = fake.deals[0]
    edited["properties"]["amount"] = "777"
    edited["properties"]["hs_lastmodifieddate"] = str(int((NOW + timedelta(minutes=1)).timestamp() * 1000))
    await jobs.incremental(conn, c, now=NOW + timedelta(minutes=15), objects=OBJECTS)
    with conn.cursor() as cur:
        cur.execute("select amount from silver.deal where hs_deal_id=%s", (edited["id"],))
        assert int(cur.fetchone()["amount"]) == 777


def test_weekly_snapshot_is_idempotent(conn):  # FR-ING-4
    from omnidata.ingest.seed import seed
    seed(conn, deals=50)
    d = datetime(2026, 9, 14, tzinfo=UTC).date()
    n1 = jobs.weekly_snapshot(conn, d)
    n2 = jobs.weekly_snapshot(conn, d)
    assert n1 == n2 == 50 == count(conn, "silver.deal_snapshot")


def test_seed_and_audit_report(conn):  # FR-ING-5 + dev seed
    from omnidata.ingest.seed import seed
    seed(conn, deals=400)
    r = readiness(conn)
    ucs = {u.name: u.decision for u in r.use_cases}
    assert ucs["Quota forecast"] == "go" and ucs["Script adherence"] == "no-go"
    assert r.pct_intact_stage_history == 1.0 and r.lost_deals > 0


def test_migrations_are_forward_only_and_rls_has_no_policies(conn):
    from omnidata import db
    assert db.migrate(conn) == []  # second run applies nothing
    with conn.cursor() as cur:
        cur.execute("select count(*) n from pg_tables where schemaname in ('bronze','silver','app') and not rowsecurity")
        assert cur.fetchone()["n"] == 0
        cur.execute("select count(*) n from pg_policies where schemaname in ('bronze','silver','app')")
        assert cur.fetchone()["n"] == 0
        cur.execute("select count(*) n from information_schema.columns where table_schema='silver' "
                    "and table_name='deal' and column_name='org_id'")
        assert cur.fetchone()["n"] == 1


def test_advisory_lock_blocks_second_runner(conn):
    from omnidata import db
    other = db.connect(conn.info.dsn.replace("password=", "password="))
    try:
        with advisory_lock(conn, 4242), pytest.raises(RuntimeError):
            with advisory_lock(other, 4242):
                pass
    finally:
        other.close()
