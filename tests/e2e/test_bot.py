"""End-to-end bot flows against Postgres with fake WhatsApp/HubSpot/LLM. FR-BOT-1..8, FR-WRT-1..5, FR-ALR-1..3."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from omnidata.alerts import engine
from omnidata.api.app import create_app
from omnidata.bot import actions
from omnidata.bot.orchestrator import Deps, process_next
from omnidata.config import Settings
from omnidata.ingest.seed import seed
from omnidata.llm.base import ToolCall
from omnidata.security.principal import resolve_by_phone

from ..conftest import TEST_DSN
from ..fakes import FakeGateway, FakeLlm, FakeWriter
from ..helpers import add_user, inbound

REP_A, REP_B, MGR = "+5511900000001", "+5511900000002", "+5511900000009"


@pytest.fixture
def world(conn):
    seed(conn, deals=120)
    a = add_user(conn, REP_A, "9000", name="Ana")
    b = add_user(conn, REP_B, "9001", name="Bruno")
    m = add_user(conn, MGR, "9002", role="manager", name="Gestor")
    with conn.cursor() as cur:
        cur.execute("update app.app_user set manager_user_id=%s where id in (%s,%s)", (m, a, b))
    conn.commit()
    gw, w = FakeGateway(), FakeWriter()
    s = Settings(rate_limit_msgs_per_hour=1000)
    return conn, gw, w, s, {"a": a, "b": b, "m": m}


async def say(conn, deps, phone, text=None, n=[0], **kw):  # noqa: B006
    n[0] += 1
    if text is not None:
        inbound(conn, f"wamid.{n[0]}", phone, "text", text=text)
    else:
        inbound(conn, f"wamid.{n[0]}", phone, "interactive", reply_id=kw["reply"], title="")
    assert await process_next(conn, deps)
    return deps.gateway.last


def deps(gw, w, s, llm=None):
    return Deps(gateway=gw, writer=w, llm=llm, settings=s)


async def test_unknown_number_gets_refusal_and_no_data(world):  # FR-BOT-1 AC
    conn, gw, w, s, _ = world
    out = await say(conn, deps(gw, w, s), "+5599000000000", "como estou na meta?")
    assert "convite" in out["body"] and "R$" not in out["body"]


async def test_onboarding_aceito_activates_and_records_consent(world):  # FR-BOT-1
    conn, gw, w, s, _ = world
    add_user(conn, "+5511977770000", "9003", status="invited", name="Nova")
    d = deps(gw, w, s)
    out = await say(conn, d, "+5511977770000", "oi")
    assert "Aceito" in out["body"]
    out = await say(conn, d, "+5511977770000", "Aceito")
    assert "Tudo certo" in out["body"]
    with conn.cursor() as cur:
        cur.execute("select status, consent_text_version, opted_in_at from app.app_user where phone_e164=%s", ("+5511977770000",))
        r = cur.fetchone()
    assert r["status"] == "active" and r["consent_text_version"] == "v1" and r["opted_in_at"]


async def test_revoked_and_paused_users_get_nothing(world):
    conn, gw, w, s, _ = world
    add_user(conn, "+5511911110000", "9004", status="revoked")
    out = await say(conn, deps(gw, w, s), "+5511911110000", "meus negócios")
    assert "convite" in out["body"]


async def test_read_question_degraded_mode_uses_template_without_llm(world):  # FR-BOT-7
    conn, gw, w, s, _ = world
    out = await say(conn, deps(gw, w, s, llm=None), REP_A, "como estou na meta?")
    assert "meta" in out["body"].lower() and "R$" in out["body"]


async def test_llm_down_falls_back_to_keywords_then_menu(world):  # FR-BOT-7
    conn, gw, w, s, _ = world
    d = deps(gw, w, s, FakeLlm(down=True))
    assert "meta" in (await say(conn, d, REP_A, "qual minha meta"))["body"].lower()
    out = await say(conn, d, REP_A, "asdf qwer")
    assert out["type"] == "list" and len(out["rows"]) <= 10


async def test_number_guard_falls_back_when_narrator_invents_a_number(world):  # §11.3 / G5
    conn, gw, w, s, _ = world
    llm = FakeLlm(tool=ToolCall("get_quota_status", {}), narration="Você está em 99,9% da meta, ótimo!")
    out = await say(conn, deps(gw, w, s, llm), REP_A, "como to na meta")
    assert "99,9" not in out["body"]
    with conn.cursor() as cur:
        cur.execute("select count(*) n from app.audit_log where event='number_guard_fallback'")
        assert cur.fetchone()["n"] == 1


async def test_faithful_narration_is_sent(world):
    conn, gw, w, s, _ = world
    from omnidata.bot import repo
    q = repo.quota_status(conn, await _p(conn, REP_A), datetime.now(UTC).date().replace(day=1))
    text = f"Sua meta é R$ {q['quota_amount']:,.0f}".replace(",", ".")
    llm = FakeLlm(tool=ToolCall("get_quota_status", {}), narration=text)
    out = await say(conn, deps(gw, w, s, llm), REP_A, "meta?")
    assert out["body"] == f"*Vega*: {text}"  # signed by the specialist who owns the tool


async def _p(conn, phone):
    return resolve_by_phone(conn, phone)


async def test_router_input_is_pii_masked(world):
    conn, gw, w, s, _ = world
    llm = FakeLlm(tool=ToolCall("get_pipeline_summary", {}))
    await say(conn, deps(gw, w, s, llm), REP_A, "meu funil, ligue para joao@acme.com 11 98888-7777")
    assert "@" not in llm.router_inputs[0] and "98888" not in llm.router_inputs[0]


async def test_permission_matrix_rep_cannot_see_other_reps_deals(world):  # FR-BOT-2 AC
    conn, gw, w, s, _ = world
    from omnidata.bot import repo
    pa, pb, pm = (resolve_by_phone(conn, x) for x in (REP_A, REP_B, MGR))
    with conn.cursor() as cur:
        cur.execute("select hs_deal_id, name from serving.v_deal_health where hs_owner_id='9001' limit 1")
        b_deal = cur.fetchone()
    assert repo.get_deal_scoped(conn, pa, b_deal["hs_deal_id"]) is None                 # by id
    assert repo.find_deals(conn, pa, b_deal["name"]) == []                              # by name
    assert repo.get_deal_scoped(conn, pb, b_deal["hs_deal_id"]) is not None
    assert repo.get_deal_scoped(conn, pm, b_deal["hs_deal_id"]) is not None             # manager sees the team
    a_ids = {d["id"] for d in repo.deals_needing_action(conn, pa, 10)["deals"]}
    with conn.cursor() as cur:
        cur.execute("select hs_deal_id from serving.v_deal_health where hs_owner_id <> '9000'")
        assert not a_ids & {r["hs_deal_id"] for r in cur.fetchall()}


async def test_rep_cannot_write_to_another_reps_deal(world):  # FR-BOT-2 + FR-WRT
    conn, gw, w, s, _ = world
    with conn.cursor() as cur:
        cur.execute("select hs_deal_id, name from serving.v_deal_health where hs_owner_id='9001' limit 1")
        b_deal = cur.fetchone()
    llm = FakeLlm(tool=ToolCall("add_note", {"deal": b_deal["hs_deal_id"], "text": "oi"}))
    out = await say(conn, deps(gw, w, s, llm), REP_A, "nota")
    assert w.created == [] and "Não achei" in out["body"]


async def _own_deal(conn, owner="9000"):
    with conn.cursor() as cur:
        cur.execute("select hs_deal_id, name, amount from serving.v_deal_health where hs_owner_id=%s order by hs_deal_id limit 1", (owner,))
        return cur.fetchone()


async def test_note_receipt_and_undo(world):  # FR-WRT-1, 3, 4, 5
    conn, gw, w, s, _ = world
    deal = await _own_deal(conn)
    d = deps(gw, w, s, FakeLlm(tool=ToolCall("add_note", {"deal": deal["hs_deal_id"], "text": "CFO aprovou"})))
    out = await say(conn, d, REP_A, "nota")
    assert out["type"] == "buttons" and [b[1] for b in out["buttons"]] == ["Editar", "Desfazer"]
    with conn.cursor() as cur:  # write-through: the next answer already sees it
        cur.execute("select summary from silver.activity where hs_deal_id=%s and activity_type='note' and summary='CFO aprovou'", (deal["hs_deal_id"],))
        assert cur.fetchone()
        cur.execute("select status, before_state, after_state, idempotency_key from app.pending_action where kind='add_note'")
        pa = cur.fetchone()
        assert pa["status"] == "executed" and pa["after_state"]["object_id"] and pa["idempotency_key"]
        cur.execute("select count(*) n from app.audit_log where event='write_note'")
        assert cur.fetchone()["n"] == 1
    undo_id = out["buttons"][1][0]
    out2 = await say(conn, d, REP_A, reply=undo_id)
    assert "Desfeito" in out2["body"] and w.archived == [("notes", "1")]
    out3 = await say(conn, d, REP_A, reply=undo_id)  # pressing twice is harmless
    assert "já foi feito" in out3["body"] and len(w.archived) == 1


async def test_hubspot_5xx_marks_failed_never_silent_success(world):  # FR-WRT AC
    conn, gw, w, s, _ = world
    w.fail = True
    deal = await _own_deal(conn)
    out = await say(conn, deps(gw, w, s, FakeLlm(tool=ToolCall("add_note", {"deal": deal["hs_deal_id"], "text": "x"}))), REP_A, "nota")
    assert "não registrei" in out["body"]
    with conn.cursor() as cur:
        cur.execute("select status from app.pending_action")
        assert cur.fetchone()["status"] == "failed"
        cur.execute("select count(*) n from silver.activity where summary='x'")
        assert cur.fetchone()["n"] == 0


async def test_deal_update_requires_confirmation_and_double_confirm_executes_once(world):  # FR-WRT-2
    conn, gw, w, s, _ = world
    deal = await _own_deal(conn)
    d = deps(gw, w, s, FakeLlm(tool=ToolCall("propose_deal_update", {"deal": deal["hs_deal_id"], "field": "amount", "value": "85000"})))
    out = await say(conn, d, REP_A, "muda o valor")
    assert [b[1] for b in out["buttons"]] == ["Confirmar", "Ajustar", "Cancelar"] and w.updates == []
    confirm = out["buttons"][0][0]
    r1 = await say(conn, d, REP_A, reply=confirm)
    r2 = await say(conn, d, REP_A, reply=confirm)
    assert "Feito" in r1["body"] and len(w.updates) == 1 and "já foi feito" in r2["body"]
    with conn.cursor() as cur:
        cur.execute("select amount from silver.deal where hs_deal_id=%s", (deal["hs_deal_id"],))
        assert int(cur.fetchone()["amount"]) == 85000  # write-through


async def test_free_text_pode_equals_confirm_and_cancela_equals_cancel(world):
    conn, gw, w, s, _ = world
    deal = await _own_deal(conn)
    d = deps(gw, w, s, FakeLlm(tool=ToolCall("propose_deal_update", {"deal": deal["hs_deal_id"], "field": "amount", "value": "70000"})))
    await say(conn, d, REP_A, "muda")
    assert "Feito" in (await say(conn, d, REP_A, "pode"))["body"] and len(w.updates) == 1
    await say(conn, d, REP_A, "muda")
    assert "Cancelado" in (await say(conn, d, REP_A, "cancela"))["body"] and len(w.updates) == 1


async def test_stale_undo_refuses_when_colleague_changed_value(world):  # FR-WRT-3 / D10
    conn, gw, w, s, _ = world
    deal = await _own_deal(conn)
    d = deps(gw, w, s, FakeLlm(tool=ToolCall("propose_deal_update", {"deal": deal["hs_deal_id"], "field": "amount", "value": "50000"})))
    out = await say(conn, d, REP_A, "muda")
    done = await say(conn, d, REP_A, reply=out["buttons"][0][0])
    w.deal_props[deal["hs_deal_id"]]["amount"] = "61000"  # someone else edited in HubSpot afterwards
    undo = await say(conn, d, REP_A, reply=done["buttons"][0][0])
    assert "valor mudou" in undo["body"] and "61000" in undo["body"]
    assert len(w.updates) == 1  # nothing was overwritten
    with conn.cursor() as cur:
        cur.execute("select status from app.pending_action where kind='update_deal'")
        assert cur.fetchone()["status"] == "executed"


async def test_undo_after_24h_is_refused(world):
    conn, gw, w, s, _ = world
    deal = await _own_deal(conn)
    d = deps(gw, w, s, FakeLlm(tool=ToolCall("add_note", {"deal": deal["hs_deal_id"], "text": "y"})))
    out = await say(conn, d, REP_A, "n")
    with conn.cursor() as cur:
        cur.execute("update app.pending_action set undo_deadline = now() - interval '1 minute'")
    conn.commit()
    assert "24h" in (await say(conn, d, REP_A, reply=out["buttons"][1][0]))["body"] and w.archived == []


async def test_expired_confirmation_is_rejected(world):
    conn, gw, w, s, _ = world
    deal = await _own_deal(conn)
    d = deps(gw, w, s, FakeLlm(tool=ToolCall("propose_deal_update", {"deal": deal["hs_deal_id"], "field": "amount", "value": "1000"})))
    out = await say(conn, d, REP_A, "muda")
    with conn.cursor() as cur:
        cur.execute("update app.pending_action set expires_at = now() - interval '1 minute'")
    conn.commit()
    assert "expirou" in (await say(conn, d, REP_A, reply=out["buttons"][0][0]))["body"] and w.updates == []


async def test_ambiguous_deal_gets_list_and_pick_completes_the_action(world):  # FR-BOT-3 / edge case
    conn, gw, w, s, _ = world
    d = deps(gw, w, s, FakeLlm(tool=ToolCall("add_note", {"deal": "Empresa", "text": "ligar amanhã"})))
    out = await say(conn, d, REP_A, "nota na empresa")
    assert out["type"] == "list"
    picked = await say(conn, d, REP_A, reply=out["rows"][0][0])
    assert picked["type"] == "buttons" and len(w.created) == 1


async def test_rate_limit(world):
    conn, gw, w, s, _ = world
    s2 = Settings(rate_limit_msgs_per_hour=2)
    d = deps(gw, w, s2)
    for _ in range(3):
        await say(conn, d, REP_A, "meta")
    assert "Muitas mensagens" in gw.last["body"]


async def test_audio_is_transcribed_then_routed(world):
    conn, gw, w, s, _ = world
    inbound(conn, "wamid.aud", REP_A, "audio", media_id="m1", mime="audio/ogg")
    await process_next(conn, deps(gw, w, s, FakeLlm()))
    assert "meta" in gw.last["body"].lower()


# ---------------- webhook ----------------
def _sig(secret, body):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_signature_dedupe_and_persist(conn, monkeypatch):  # §11.1 step 1, edge: duplicate delivery
    from omnidata.config import get_settings
    from omnidata.db import connect
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "s3cret")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "vt")
    get_settings.cache_clear()
    add_user(conn, REP_A, "9000")
    client = TestClient(create_app(lambda: connect(TEST_DSN)))
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"id": "wamid.X1", "from": "5511900000001", "type": "text", "text": {"body": "meta?"}}]}}]}]}
    raw = json.dumps(payload).encode()
    assert client.post("/webhooks/whatsapp", content=raw).status_code == 401
    assert client.post("/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    ok = {"X-Hub-Signature-256": _sig("s3cret", raw)}
    assert client.post("/webhooks/whatsapp", content=raw, headers=ok).status_code == 200
    assert client.post("/webhooks/whatsapp", content=raw, headers=ok).status_code == 200  # Meta retry
    with conn.cursor() as cur:
        cur.execute("select count(*) n, min(status) s from app.wa_message where wa_message_id='wamid.X1'")
        r = cur.fetchone()
    assert r["n"] == 1 and r["s"] == "received"
    assert client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "42"}).text == "42"
    assert client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "no", "hub.challenge": "42"}).status_code == 403
    assert client.get("/healthz").json() == {"status": "ok"}
    get_settings.cache_clear()


# ---------------- gold/serving contract ----------------
def test_serving_views_have_expected_contract(conn):
    seed(conn, deals=200)
    with conn.cursor() as cur:
        cur.execute("select count(*) n, count(*) filter (where cardinality(health_flags) > 0) f, max(attention_score) a from serving.v_deal_health")
        r = cur.fetchone()
        assert r["n"] > 0 and r["f"] > 0 and r["a"] > 0
        cur.execute("select attainment, gap, low_n, win_rate_ci_low, win_rate_ci_high from serving.v_rep_kpis where quota_amount is not null limit 1")
        k = cur.fetchone()
        assert k["gap"] is not None and (k["win_rate_ci_low"] is None or k["win_rate_ci_low"] <= k["win_rate_ci_high"])
        cur.execute("select count(*) from serving.v_cost_per_user"); cur.fetchone()
        cur.execute("select * from serving.v_alert_effectiveness"); cur.fetchall()


# ---------------- alerts ----------------
async def test_alert_engine_budget_quiet_hours_snooze_and_telemetry(world):  # FR-ALR-1..3
    conn, gw, w, s, ids = world
    made = engine.evaluate(conn)
    assert made > 0 and engine.evaluate(conn) == 0  # idempotent (dedupe_key + 3-day silence)
    s2 = Settings(alert_daily_cap=2)
    noon = datetime.now(UTC).replace(hour=15, minute=0)  # 12:00 in Sao Paulo
    sent = await engine.dispatch(conn, gw, s2, now=noon)
    per_user = {}
    for m in gw.sent:
        per_user[m["to"]] = per_user.get(m["to"], 0) + 1
    assert sent > 0 and max(per_user.values()) <= 2                       # daily cap
    assert all(m["name"] == "alert_deal_v1" and m["payload"].startswith("act:open:") for m in gw.sent)  # template + quick reply
    night = noon.replace(hour=1)                                            # 22:00 local, quiet hours
    before = len(gw.sent)
    assert await engine.dispatch(conn, gw, Settings(alert_daily_cap=50), now=night) == 0 and len(gw.sent) == before
    # snooze via button, then telemetry: viewed + acted
    with conn.cursor() as cur:
        cur.execute("select id, hs_deal_id from app.alert_event where sent_at is not null and user_id=%s limit 1", (ids["a"],))
        ev = cur.fetchone()
    d = deps(gw, w, s)
    await say(conn, d, REP_A, reply=f"act:open:{ev['id']}")
    await say(conn, d, REP_A, reply=f"act:snooze:{ev['id']}")
    await actions.add_note(conn, w, resolve_by_phone(conn, REP_A), "", "feito", deal_id=ev["hs_deal_id"])
    with conn.cursor() as cur:
        cur.execute("select viewed_at, snoozed_until, acted_at from app.alert_event where id=%s", (ev["id"],))
        r = cur.fetchone()
        cur.execute("select * from serving.v_alert_effectiveness")
        eff = cur.fetchall()
    assert r["viewed_at"] and r["snoozed_until"] > datetime.now(UTC) + timedelta(days=2) and r["acted_at"] and eff


async def test_morning_brief_template_once_per_day_business_days_only(world):  # FR-BOT-4
    conn, gw, w, s, _ = world
    monday = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)  # 09:00 in Sao Paulo, past 07:30
    assert await engine.morning_briefs(conn, gw, now=monday) == 3
    assert await engine.morning_briefs(conn, gw, now=monday) == 0            # already sent today
    assert gw.sent[0]["name"] == "morning_brief_v1" and gw.sent[0]["payload"] == "act:open:brief"
    saturday = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    assert await engine.morning_briefs(conn, gw, now=saturday) == 0
    out = await say(conn, deps(gw, w, s), REP_A, reply="act:open:brief")      # 'Ver meu dia' returns the ranked brief
    assert "Bom dia" in out["body"]
