"""Airbyte integration: API client (mock transport), landed-table ingestion (real Postgres, Airbyte-shaped tables) and generic mapping.
Fixture tables mimic Airbyte's Postgres destination v2: quoted case-preserved columns, `properties_*` flattening, JSONB arrays,
`_airbyte_raw_id` / `_airbyte_extracted_at` (shapes verified against airbyte/source-hubspot 6.9.2)."""
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from omnidata.integrations.airbyte import generic, landing
from omnidata.integrations.airbyte.client import AirbyteClient, AirbyteError, api_base

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


# ---------------- API client ----------------
def client(handler, clock=None):
    async def nosleep(_): ...
    return AirbyteClient("http://localhost:8000", "cid", "sec", transport=httpx.MockTransport(handler), clock=clock or (lambda: 0.0), sleep=nosleep)


def test_api_base_cloud_vs_self_managed():
    assert api_base("https://api.airbyte.com") == "https://api.airbyte.com/v1"
    assert api_base("http://localhost:8000/") == "http://localhost:8000/api/public/v1"
    assert api_base("https://airbyte.acme.com") == "https://airbyte.acme.com/api/public/v1"


async def test_token_request_shape_caching_and_job_trigger():
    seen = []

    def h(req):
        seen.append((req.method, req.url.path, json.loads(req.content) if req.content else None, req.headers.get("authorization")))
        if req.url.path.endswith("/applications/token"):
            return httpx.Response(200, json={"access_token": "T1", "token_type": "Bearer", "expires_in": 900})
        return httpx.Response(200, json={"jobId": 42, "status": "pending", "jobType": "sync", "connectionId": "c-1"})
    c = client(h)
    job = await c.trigger_sync("c-1")
    await c.trigger_sync("c-1")
    assert seen[0][:3] == ("POST", "/api/public/v1/applications/token", {"client_id": "cid", "client_secret": "sec", "grant-type": "client_credentials"})
    assert seen[1] == ("POST", "/api/public/v1/jobs", {"connectionId": "c-1", "jobType": "sync"}, "Bearer T1")
    assert sum(1 for s in seen if s[1].endswith("/token")) == 1 and job.id == 42 and job.status == "pending" and not job.done


async def test_expired_token_is_refreshed_once_on_401():
    tokens, calls = [], []

    def h(req):
        if req.url.path.endswith("/token"):
            tokens.append(1)
            return httpx.Response(200, json={"access_token": f"T{len(tokens)}", "expires_in": 900})
        calls.append(req.headers["authorization"])
        return httpx.Response(401) if len(calls) == 1 else httpx.Response(200, json={"data": [{"connectionId": "c", "name": "hubspot"}]})
    assert (await client(h).list_connections())[0]["name"] == "hubspot" and calls == ["Bearer T1", "Bearer T2"]


async def test_wait_polls_until_terminal_and_times_out():
    states = iter(["pending", "running", "succeeded"])

    def h(req):
        if req.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "T", "expires_in": 900})
        return httpx.Response(200, json={"jobId": 7, "status": next(states), "rowsSynced": 1500})
    job = await client(h).wait(7)
    assert job.ok and job.rows_synced == 1500
    t = iter(range(0, 10_000, 100))
    with pytest.raises(AirbyteError):
        await client(lambda r: httpx.Response(200, json={"access_token": "T"}) if r.url.path.endswith("/token") else httpx.Response(200, json={"jobId": 1, "status": "running"}),
                     clock=lambda: float(next(t))).wait(1, timeout=300)


async def test_errors_never_leak_credentials():
    with pytest.raises(AirbyteError) as e:
        await client(lambda r: httpx.Response(403, text="nope sec cid")).list_connections()
    assert "sec" not in str(e.value) and "cid" not in str(e.value)


# ---------------- landed tables -> silver ----------------
DDL = """
create schema airbyte;
create table airbyte.owners ("id" text, "email" text, "firstName" text, "lastName" text, "archived" boolean,
  "_airbyte_raw_id" text, "_airbyte_extracted_at" timestamptz, "_airbyte_meta" jsonb);
create table airbyte.deal_pipelines ("pipelineId" text, "label" text, "stages" jsonb,
  "_airbyte_raw_id" text, "_airbyte_extracted_at" timestamptz, "_airbyte_meta" jsonb);
create table airbyte.deals ("id" text, "createdAt" timestamptz, "updatedAt" timestamptz, "archived" boolean, "contacts" jsonb, "companies" jsonb,
  "properties_dealname" text, "properties_amount" numeric, "properties_pipeline" text, "properties_dealstage" text,
  "properties_closedate" timestamptz, "properties_hubspot_owner_id" text, "properties_closed_lost_reason" text,
  "properties_hs_lastmodifieddate" timestamptz, "properties_num_associated_contacts" numeric,
  "_airbyte_raw_id" text, "_airbyte_extracted_at" timestamptz, "_airbyte_meta" jsonb);
create table airbyte.deals_property_history ("dealId" text, "property" text, "timestamp" timestamptz, "value" text, "sourceType" text,
  "_airbyte_raw_id" text, "_airbyte_extracted_at" timestamptz, "_airbyte_meta" jsonb);
create table airbyte.engagements_notes ("id" text, "archived" boolean, "deals" jsonb, "contacts" jsonb, "companies" jsonb,
  "properties_hs_note_body" text, "properties_hs_timestamp" timestamptz, "properties_hubspot_owner_id" text, "properties_hs_lastmodifieddate" timestamptz,
  "_airbyte_raw_id" text, "_airbyte_extracted_at" timestamptz, "_airbyte_meta" jsonb);
"""


def land(conn, deals=3, at=T0):
    with conn.cursor() as cur:
        cur.execute("drop schema if exists airbyte cascade")
        cur.execute(DDL)
        cur.execute("""insert into airbyte.owners values ('9001','ana@example.invalid','Ana','Souza',false,'o1',%s,'{}')""", (at,))
        stages = json.dumps([
            {"stageId": "s1", "label": "Qualificação", "displayOrder": 0, "metadata": {"isClosed": "false", "probability": "0.2"}},
            {"stageId": "won", "label": "Ganho", "displayOrder": 1, "metadata": {"isClosed": "true", "probability": "1.0"}},
            {"stageId": "lost", "label": "Perdido", "displayOrder": 2, "metadata": {"isClosed": "true", "probability": "0.0"}}])
        cur.execute("insert into airbyte.deal_pipelines values ('default','Vendas',%s,'p1',%s,'{}')", (stages, at))
        for i in range(deals):
            stage = ["s1", "won", "lost"][i % 3]
            cur.execute("insert into airbyte.deals values (%s,%s,%s,false,%s,%s,%s,%s,'default',%s,%s,'9001',%s,%s,1,%s,%s,'{}')",
                        (f"D{i}", at - timedelta(days=30), at, json.dumps(["c1"]), json.dumps(["k1"]), f"Deal {i}", 1000 * (i + 1), stage,
                         at - timedelta(days=2), "price" if stage == "lost" else None, at, f"r{i}", at + timedelta(seconds=i)))
            cur.execute("insert into airbyte.deals_property_history values (%s,'dealstage',%s,'s1','CRM',%s,%s,'{}')", (f"D{i}", at - timedelta(days=20), f"h{i}a", at))
            cur.execute("insert into airbyte.deals_property_history values (%s,'dealstage',%s,%s,'CRM',%s,%s,'{}')", (f"D{i}", at - timedelta(days=3), stage, f"h{i}b", at))
        cur.execute("insert into airbyte.engagements_notes values ('N1',false,%s,%s,'[]','Cliente aprovou',%s,'9001',%s,'n1',%s,'{}')",
                    (json.dumps(["D0"]), json.dumps(["c1"]), at, at, at))
    conn.commit()


def q(conn, sql_, *a):
    with conn.cursor() as cur:
        cur.execute(sql_, a)
        return cur.fetchall()


def test_hubspot_streams_land_into_silver_with_correct_semantics(conn):
    land(conn)
    res = landing.ingest(conn, "airbyte")
    assert res["owners"] == 1 and res["deal_pipelines"] == 1 and res["deals"] == 3 and res["deals_property_history"] == 6 and res["engagements_notes"] == 1
    assert str(res["contacts"]).startswith("skipped")           # streams that are not enabled in Airbyte are skipped, not fatal
    deals = {r["hs_deal_id"]: r for r in q(conn, "select * from silver.deal order by 1")}
    assert (deals["D0"]["is_open"], deals["D1"]["is_won"], deals["D2"]["is_lost"]) == (True, True, True)   # from stage metadata, not names
    assert deals["D2"]["lost_reason_hs"] == "price" and deals["D1"]["lost_reason_hs"] is None and int(deals["D1"]["amount"]) == 2000
    assert {r["hs_stage_id"] for r in q(conn, "select hs_stage_id from silver.stage")} == {"s1", "won", "lost"}
    assert q(conn, "select count(*) n from silver.deal_stage_history")[0]["n"] == 6
    assert q(conn, "select count(*) n from silver.deal_contact")[0]["n"] == 3 and q(conn, "select count(*) n from silver.deal_company")[0]["n"] == 3
    note = q(conn, "select hs_deal_id, hs_contact_id, summary from silver.activity where activity_type='note'")[0]
    assert (note["hs_deal_id"], note["hs_contact_id"], note["summary"]) == ("D0", "c1", "Cliente aprovou")
    assert q(conn, "select first_name from silver.owner where hs_owner_id='9001'")[0]["first_name"] == "Ana"


def test_landed_data_feeds_the_serving_contract(conn):
    land(conn)
    landing.ingest(conn, "airbyte")
    assert q(conn, "select count(*) n from serving.v_deal_health")[0]["n"] == 1        # the one open deal
    k = q(conn, "select won_count, lost_count from serving.v_rep_kpis where won_count + lost_count > 0")
    assert k and k[0]["won_count"] == 1 and k[0]["lost_count"] == 1


def test_incremental_only_reads_newer_extractions_and_is_idempotent(conn):
    land(conn)
    assert landing.ingest(conn, "airbyte")["deals"] == 3
    again = landing.ingest(conn, "airbyte")
    assert again["deals"] <= 1                                                          # only the tie at the cursor may repeat
    before = q(conn, "select count(*) n from silver.deal")[0]["n"]
    with conn.cursor() as cur:                                                          # Airbyte re-syncs D0 with a new amount
        cur.execute("""update airbyte.deals set "properties_amount"=777, "_airbyte_extracted_at"=%s where id='D0'""", (T0 + timedelta(hours=1),))
    conn.commit()
    # re-read = the updated row + the row tied at the cursor (kept on purpose: never lose rows; upserts make the repeat harmless)
    assert landing.ingest(conn, "airbyte")["deals"] == 2
    assert int(q(conn, "select amount from silver.deal where hs_deal_id='D0'")[0]["amount"]) == 777
    assert q(conn, "select count(*) n from silver.deal")[0]["n"] == before
    assert landing.ingest(conn, "airbyte", full=True)["deals"] == 3                     # --full ignores cursors


def test_lowercased_columns_from_other_destinations_settings_also_work(conn):
    land(conn)
    with conn.cursor() as cur:
        for old, new in (("firstName", "firstname"), ("lastName", "lastname")):
            cur.execute(f'alter table airbyte.owners rename column "{old}" to {new}')
    conn.commit()
    landing.ingest(conn, "airbyte", streams=["owners"])
    assert q(conn, "select last_name from silver.owner")[0]["last_name"] == "Souza"


def test_bad_identifiers_are_refused():
    with pytest.raises(ValueError):
        landing._ident("airbyte; drop table x", "deals")
    with pytest.raises(ValueError):
        landing._ident("airbyte", "deals\"--")


# ---------------- generic sources -> canonical deals ----------------
def test_generic_mapping_imports_any_landed_table_through_the_same_validation(conn):
    with conn.cursor() as cur:
        cur.execute("create schema airbyte")
        cur.execute('create table airbyte.opportunity ("Id" text, "Name" text, "StageName" text, "Amount" numeric, "CloseDate" date, "OwnerId" text)')
        cur.execute("""insert into airbyte.opportunity values
          ('006A','Acme','Prospecting',5000,'2026-12-01','Ana Souza'), ('006B','Beta','Closed Won',9000,'2026-08-10','Ana Souza'),
          ('006C','Gama','Closed Lost',1200,'2026-07-01','Bruno Lima')""")
    conn.commit()
    spec = {"name": "salesforce", "kind": "deals", "table": "airbyte.opportunity", "replace": True, "import_notes": False,
            "columns": {"id": "Id", "name": "Name", "stage": "StageName", "amount": "Amount", "close_date": "CloseDate", "owner": "OwnerId"}}
    dry = generic.run_one(conn, spec, apply=False)
    assert dry.status == "validated" and dry.report.summary["open"] == 1 and q(conn, "select count(*) n from silver.deal")[0]["n"] == 0
    res = generic.run_one(conn, spec, apply=True)
    assert res.status == "imported"
    rows = {r["hs_deal_id"]: r for r in q(conn, "select * from silver.deal")}
    assert set(rows) == {"salesforce:006A", "salesforce:006B", "salesforce:006C"}          # ids never collide with HubSpot or uploads
    assert rows["salesforce:006B"]["is_won"] and rows["salesforce:006C"]["is_lost"] and rows["salesforce:006A"]["is_open"]
    assert {r["hs_pipeline_id"] for r in rows.values()} == {"salesforce"}
    generic.run_one(conn, spec, apply=True)                                                  # snapshot semantics: idempotent
    assert q(conn, "select count(*) n from silver.deal")[0]["n"] == 3


def test_generic_config_is_validated_against_injection():
    for bad in ({"name": "x", "kind": "deals", "table": "a.b", "columns": {"id": "Id; drop table x"}},
                {"name": "x", "kind": "deals", "table": "a.b;--", "columns": {"id": "Id"}},
                {"name": "x", "kind": "deals", "table": "a.b", "columns": {"not_a_field": "Id"}},
                {"name": "x", "kind": "nope", "table": "a.b", "columns": {}}):
        with pytest.raises(ValueError):
            generic._check(bad)


def test_shipped_generic_templates_are_disabled_and_well_formed():
    cfg = generic.load_config()
    assert cfg["airbyte"]["hubspot"]["connector"].endswith("6.9.2")
    for spec in cfg["generic"]:
        assert spec["enabled"] is False              # templates never run until someone inspects the real table
        generic._check(spec)
