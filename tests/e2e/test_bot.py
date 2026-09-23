"""End-to-end bot flows against Postgres with fake WhatsApp/HubSpot/LLM. FR-BOT-1..8, FR-WRT-1..5, FR-ALR-1..3."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from omnidata.alerts import engine
from omnidata.api.app import create_app
from omnidata.bot import actions
from omnidata.bot import strings_ptbr as S
from omnidata.bot.orchestrator import Deps, process_next
from omnidata.config import Settings
from omnidata.ingest.seed import seed
from omnidata.llm.base import ToolCall
from omnidata.security.principal import resolve_by_phone

from ..conftest import TEST_DSN
from ..fakes import FakeEmbeddings, FakeGateway, FakeLlm, FakeVectorStore, FakeWriter
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
    assert "Orion" in out["body"] and "Nova" in out["body"]
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


async def test_llm_false_negative_oos_gets_a_second_opinion_from_keywords(world):
    # real bug found in production: "gera o script a partir disso" (a context-dependent follow-up the stateless
    # router can't resolve) made the LLM say FORA_DO_ESCOPO even though "script" is a clear nova.get_playbook match
    conn, gw, w, s, _ = world
    llm = FakeLlm(tool=None, router_text="FORA_DO_ESCOPO", narration="Prepare uma resposta para a objeção de preço.")
    out = await say(conn, deps(gw, w, s, llm), REP_A, "gera o script a partir disso")
    assert out["body"].startswith("*Nova*:")


async def test_llm_oos_still_wins_when_keywords_also_find_nothing(world):
    conn, gw, w, s, _ = world
    llm = FakeLlm(tool=None, router_text="FORA_DO_ESCOPO")
    out = await say(conn, deps(gw, w, s, llm), REP_A, "qual a previsão do tempo em São Paulo?")
    assert out["body"] == f"*Orion*: {S.OUT_OF_SCOPE}"


async def test_set_goal_then_get_goal_status_shows_real_progress(world):
    conn, gw, w, s, _ = world
    llm = FakeLlm(tool=ToolCall("set_goal", {"goal_type": "deals_won", "target": 2, "deadline_in_days": 5}))
    out = await say(conn, deps(gw, w, s, llm), REP_A, "quero fechar 2 negócios essa semana")
    assert out["body"].startswith("*Aurora*: Combinado!") and "fechar 2 negócio(s)" in out["body"]

    llm2 = FakeLlm(tool=ToolCall("get_goal_status", {}))
    out2 = await say(conn, deps(gw, w, s, llm2), REP_A, "como está minha meta pessoal?")
    assert out2["body"].startswith("*Aurora*: Sua meta pessoal (fechar 2 negócio(s)): 0 até agora,")


async def test_morning_brief_includes_the_goal_line_only_when_active(world):
    conn, gw, w, s, ids = world
    llm = FakeLlm(tool=ToolCall("get_morning_brief", {}))
    out = await say(conn, deps(gw, w, s, llm), REP_A, "bom dia")
    assert "meta pessoal" not in out["body"]

    with conn.cursor() as cur:
        cur.execute("insert into app.seller_goal (user_id, hs_owner_id, goal_type, target, deadline) values (%s,'9000','deals_won',2,%s)",
                    (ids["a"], datetime.now(UTC).date()))
    conn.commit()
    out2 = await say(conn, deps(gw, w, s, llm), REP_A, "bom dia")
    assert "meta pessoal" in out2["body"]


async def test_nova_can_also_search_meeting_notes_and_gets_signed_correctly(world):
    # search_meeting_notes now has two legal owners (nova, atlas) — the reply must credit whichever Orion actually
    # planned, not always default to atlas (a real gap: _run_tool used to derive the signer from a global 1:1 map)
    conn, gw, w, s, ids = world
    with conn.cursor() as cur:
        cur.execute("insert into app.meeting_transcript (id, hs_deal_id, hs_owner_id, deal_name, occurred_at, text) "
                    "values ('11111111-1111-1111-1111-111111111111', 'D1', '9000', 'Acme', now(), 'cliente reclamou do preço')")
    conn.commit()
    store = FakeVectorStore()
    store.upsert(["11111111-1111-1111-1111-111111111111"], [[1.0, 0.0, 0.0, 0.0]], [{"hs_owner_id": "9000"}])
    llm = FakeLlm(tool=ToolCall("plan", {"steps": [{"agent": "nova", "tool": "search_meeting_notes", "args": {"query": "preço"}}]}))
    deps_ = Deps(gateway=gw, writer=w, llm=llm, settings=s, embeddings=FakeEmbeddings(), vector_store=store)
    out = await say(conn, deps_, REP_A, "o que foi dito sobre preço nas reuniões?")
    assert out["body"].startswith("*Nova*:")


async def test_bare_thanks_gets_a_reaction_not_a_reply(world):  # humanized flow: "valeu" shouldn't hit the menu fallback
    conn, gw, w, s, _ = world
    inbound(conn, "wamid.thanks", REP_A, "text", text="valeu!")
    assert await process_next(conn, deps(gw, w, s))
    assert gw.reacted == [(REP_A, "wamid.thanks", "👍")]
    assert gw.sent == []


async def test_typing_delay_is_off_by_default(world):
    conn, gw, w, s, _ = world
    llm = FakeLlm(tool=ToolCall("get_quota_status", {}), narration="Você está em 50% da meta.")
    await say(conn, deps(gw, w, s, llm), REP_A, "meta?")
    assert gw.presence == []  # no TYPING_DELAY_MAX_SECONDS configured: today's behavior is unchanged


async def test_typing_delay_sends_presence_before_the_reply(world):
    conn, gw, w, _, _ = world
    s = Settings(rate_limit_msgs_per_hour=1000, typing_delay_max_seconds=0.01)
    llm = FakeLlm(tool=ToolCall("get_quota_status", {}), narration="Você está em 50% da meta.")
    await say(conn, deps(gw, w, s, llm), REP_A, "meta?")
    assert gw.presence == [(REP_A, True)]
    assert gw.sent  # the real reply still goes out after the (tiny, test-only) pause


async def test_negative_sentiment_shapes_the_narrator_tone_not_the_numbers(world):
    conn, gw, w, s, _ = world
    llm = FakeLlm(tool=ToolCall("get_quota_status", {}), narration="Você está em 50% da meta.")
    await say(conn, deps(gw, w, s, llm), REP_A, "isso não está funcionando, péssimo")
    assert "frustrado" in llm.narrator_systems[-1]
    assert "frustrado" not in gw.last["body"]  # tone hint only ever shapes the persona prompt, never leaks into the reply


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


async def test_audio_is_transcribed_echoed_routed_and_costed(world):  # FR-BOT-5
    from ..fakes import FakeTranscriber
    conn, gw, w, s, _ = world
    inbound(conn, "wamid.aud", REP_A, "audio", media_id="m1", mime="audio/ogg")
    d = Deps(gateway=gw, writer=w, llm=None, settings=s, transcriber=FakeTranscriber("como estou na meta"))
    await process_next(conn, d)
    assert gw.last["body"].startswith("🎤 Entendi: “como estou na meta”") and "*Vega*:" in gw.last["body"]
    with conn.cursor() as cur:
        cur.execute("select provider, model, cost_usd from app.llm_call where purpose='transcribe'")
        r = cur.fetchone()
    assert r["provider"] == "openai" and r["model"] == "gpt-transcribe" and float(r["cost_usd"]) == 0.0009  # 12 s * $0.0045/min


async def test_audio_write_still_needs_confirmation_after_transcription(world):  # transcripts can be wrong: high-risk stays gated
    from ..fakes import FakeTranscriber
    conn, gw, w, s, _ = world
    deal = await _own_deal(conn)
    inbound(conn, "wamid.aud2", REP_A, "audio", media_id="m1")
    d = Deps(gateway=gw, writer=w, llm=FakeLlm(tool=ToolCall("propose_deal_update", {"deal": deal["hs_deal_id"], "field": "amount", "value": "99000"})),
             settings=s, transcriber=FakeTranscriber("muda o valor pra noventa e nove mil"))
    await process_next(conn, d)
    assert [b[1] for b in gw.last["buttons"]] == ["Confirmar", "Ajustar", "Cancelar"] and w.updates == []


@pytest.mark.parametrize("err,expect", [("too_long", "longo demais"), ("too_big", "grande demais"), ("api", "Não consegui entender o áudio"), ("decode", "Não consegui entender o áudio")])
async def test_audio_failures_get_a_helpful_reply_and_no_action(world, err, expect):
    from ..fakes import FakeTranscriber
    conn, gw, w, s, _ = world
    inbound(conn, "wamid.a3", REP_A, "audio", media_id="m1")
    await process_next(conn, Deps(gateway=gw, writer=w, llm=None, settings=s, transcriber=FakeTranscriber(error=err)))
    assert expect in gw.last["body"] and w.created == [] and w.updates == []


async def test_audio_without_transcriber_or_empty_or_over_budget(world):
    from ..fakes import FakeTranscriber
    conn, gw, w, s, _ = world
    inbound(conn, "wamid.a4", REP_A, "audio", media_id="m1")
    await process_next(conn, Deps(gateway=gw, writer=w, llm=None, settings=s, transcriber=None))
    assert "Não consegui entender o áudio" in gw.last["body"]
    inbound(conn, "wamid.a5", REP_A, "audio", media_id="m1")
    await process_next(conn, Deps(gateway=gw, writer=w, llm=None, settings=s, transcriber=FakeTranscriber(text="")))
    assert "Não ouvi nada" in gw.last["body"]
    with conn.cursor() as cur:  # daily transcription budget
        uid = resolve_by_phone(conn, REP_A).user_id
        cur.execute("insert into app.llm_call (user_id, purpose, provider, model, cost_usd) values (%s,'transcribe','openai','gpt-transcribe',0.5)", (uid,))
    conn.commit()
    ft = FakeTranscriber()
    inbound(conn, "wamid.a6", REP_A, "audio", media_id="m1")
    await process_next(conn, Deps(gateway=gw, writer=w, llm=None, settings=s, transcriber=ft))
    assert "limite de transcrição" in gw.last["body"] and ft.calls == 0  # no API call once over budget


# ---------------- webhook ----------------
def _upsert(msg_id: str, jid: str = "5511900000001@s.whatsapp.net", text: str = "meta?", from_me: bool = False) -> dict:
    return {"event": "messages.upsert", "instance": "omnidata",
            "data": {"key": {"id": msg_id, "remoteJid": jid, "fromMe": from_me}, "message": {"conversation": text}}}


def test_webhook_secret_dedupe_ignores_own_messages_and_persists(conn, monkeypatch):  # §11.1 step 1, ADR 0008
    from omnidata.config import get_settings
    from omnidata.db import connect
    monkeypatch.setenv("EVOLUTION_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()
    add_user(conn, REP_A, "9000")
    client = TestClient(create_app(lambda: connect(TEST_DSN)))
    raw = json.dumps(_upsert("EVT.X1")).encode()
    assert client.post("/webhooks/evolution", content=raw).status_code == 401  # no header at all
    assert client.post("/webhooks/evolution", content=raw, headers={"x-omnidata-secret": "bad"}).status_code == 401
    ok = {"x-omnidata-secret": "s3cret"}
    assert client.post("/webhooks/evolution", content=raw, headers=ok).status_code == 200
    assert client.post("/webhooks/evolution", content=raw, headers=ok).status_code == 200  # a retried delivery
    with conn.cursor() as cur:
        cur.execute("select count(*) n, min(status) s from app.wa_message where wa_message_id='EVT.X1'")
        r = cur.fetchone()
    assert r["n"] == 1 and r["s"] == "received"
    # Baileys echoes the bot's own outgoing messages back through this same webhook (fromMe: true): must never be stored as inbound
    echo = json.dumps(_upsert("EVT.OUT", from_me=True)).encode()
    assert client.post("/webhooks/evolution", content=echo, headers=ok).status_code == 200
    with conn.cursor() as cur:
        cur.execute("select count(*) n from app.wa_message where wa_message_id='EVT.OUT'")
        assert cur.fetchone()["n"] == 0
    # Real bug: the bot was replying in every WhatsApp group the connected number belongs to
    group = json.dumps(_upsert("EVT.GROUP", jid="120363012345678901@g.us")).encode()
    assert client.post("/webhooks/evolution", content=group, headers=ok).status_code == 200
    with conn.cursor() as cur:
        cur.execute("select count(*) n from app.wa_message where wa_message_id='EVT.GROUP'")
        assert cur.fetchone()["n"] == 0  # never stored, so process_next can never reply into the group
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


async def test_orion_sees_the_previous_exchange_to_resolve_a_follow_up(world):
    conn, gw, w, s, ids = world
    llm1 = FakeLlm(tool=ToolCall("get_playbook", {"topic": "objection"}), narration="Motivo de perda: preço.")
    await say(conn, deps(gw, w, s, llm1), REP_A, "preciso de um script pra uma reunião difícil")

    with conn.cursor() as cur:  # inbound() (tests/helpers.py) never sets user_id — production's real persist_inbound
        cur.execute("update app.wa_message set user_id=%s where user_id is null", (ids["a"],))  # does, via phone lookup
    conn.commit()

    llm2 = FakeLlm(tool=ToolCall("get_playbook", {"topic": "objection"}))
    await say(conn, deps(gw, w, s, llm2), REP_A, "um script para atacar essas causas")
    sent_text = llm2.router_inputs[0]
    assert "Contexto da última troca" in sent_text
    assert "reunião difícil" in sent_text and "Motivo de perda" in sent_text
    assert sent_text.endswith("Pedido atual: um script para atacar essas causas")


async def test_orion_adds_no_context_block_on_the_first_message(world):
    conn, gw, w, s, _ = world
    llm = FakeLlm(tool=ToolCall("get_quota_status", {}))
    await say(conn, deps(gw, w, s, llm), REP_A, "como estou na meta?")
    assert "Contexto" not in llm.router_inputs[0]


async def test_consecutive_steps_from_the_same_specialist_are_not_re_signed(world):
    # real bug found in a production transcript: "*Vega*: ... *Vega*: ..." when two plan steps both land on Vega
    conn, gw, w, s, _ = world
    llm = FakeLlm(tool=ToolCall("plan", {"steps": [{"agent": "vega", "tool": "get_quota_status", "args": {}},
                                                    {"agent": "vega", "tool": "get_team_status", "args": {}}]}))
    out = await say(conn, deps(gw, w, s, llm), REP_A, "meta e status do time")
    assert out["body"].count("*Vega*:") == 1


async def test_evening_recap_reports_real_progress_and_respects_the_daily_gate(world):
    conn, gw, w, s, ids = world
    monday = datetime(2026, 9, 21, 21, 0, tzinfo=UTC)  # 18:00 in Sao Paulo
    with conn.cursor() as cur:
        cur.execute("update silver.deal set is_won=true, is_open=false, closed_at=%s where hs_deal_id = "
                    "(select hs_deal_id from silver.deal where hs_owner_id='9000' and is_open limit 1)", (monday,))
    conn.commit()

    assert await engine.evening_recaps(conn, gw, now=monday) == 3
    assert await engine.evening_recaps(conn, gw, now=monday) == 0  # already sent today
    ana = next(m for m in gw.sent if m["to"] == REP_A)
    assert "fechou 1 negócio" in ana["body"]

    saturday = datetime(2026, 9, 26, 21, 0, tzinfo=UTC)
    assert await engine.evening_recaps(conn, gw, now=saturday) == 0


async def test_morning_brief_template_once_per_day_business_days_only(world):  # FR-BOT-4
    conn, gw, w, s, _ = world
    monday = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)  # 09:00 in Sao Paulo, past 07:30
    assert await engine.morning_briefs(conn, gw, now=monday) == 3
    assert await engine.morning_briefs(conn, gw, now=monday) == 0            # already sent today
    assert gw.sent[0]["name"] == "morning_brief_v1" and gw.sent[0]["payload"] == "act:open:brief"
    saturday = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    assert await engine.morning_briefs(conn, gw, now=saturday) == 0
    out = await say(conn, deps(gw, w, s), REP_A, reply="act:open:brief")      # 'Ver meu dia' returns the ranked brief
    assert any(g in out["body"] for g in ("Bom dia", "Boa tarde", "Boa noite"))  # greeting is hour-sensitive (real clock here)
