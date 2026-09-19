"""Orion + specialists end to end: plan -> validate -> execute -> one merged, signed reply. ADR 0003."""
from omnidata.llm.base import ToolCall

from ..fakes import FakeLlm
from .test_bot import REP_A, _own_deal, deps, say, world  # noqa: F401


def plan(*steps):
    return ToolCall("plan", {"steps": list(steps)})


def st(agent, tool, **args):
    return {"agent": agent, "tool": tool, "args": args}


async def test_orion_splits_request_between_vega_and_lyra_and_signs_both(world):  # noqa: F811
    conn, gw, w, s, _ = world
    deal = await _own_deal(conn)
    llm = FakeLlm(tool=plan(st("vega", "get_quota_status"), st("lyra", "add_note", deal=deal["hs_deal_id"], text="CFO aprovou")))
    out = await say(conn, deps(gw, w, s, llm), REP_A, "como estou na meta e anota no negócio que o CFO aprovou")
    assert out["type"] == "buttons" and "*Vega*:" in out["body"] and "*Lyra*:" in out["body"]
    assert out["body"].index("*Vega*") < out["body"].index("*Lyra*")
    assert [b[1] for b in out["buttons"]] == ["Editar", "Desfazer"] and len(w.created) == 1
    with conn.cursor() as cur:
        cur.execute("select agent, tool, status from app.agent_step order by step_no")
        rows = [(r["agent"], r["tool"], r["status"]) for r in cur.fetchall()]
    assert rows == [("vega", "get_quota_status", "ok"), ("lyra", "add_note", "ok")]


async def test_invalid_plan_is_never_executed_and_falls_back(world):  # noqa: F811
    conn, gw, w, s, _ = world
    llm = FakeLlm(tool=plan(st("vega", "add_note", deal="x", text="y")))  # Vega has no write tool
    out = await say(conn, deps(gw, w, s, llm), REP_A, "como está minha meta?")
    assert w.created == [] and "*Vega*:" in out["body"]                   # keyword fallback answered safely
    with conn.cursor() as cur:
        cur.execute("select count(*) n from app.agent_step where status='rejected'")
        assert cur.fetchone()["n"] == 1


async def test_two_writes_in_one_plan_are_rejected(world):  # noqa: F811
    conn, gw, w, s, _ = world
    deal = await _own_deal(conn)
    llm = FakeLlm(tool=plan(st("lyra", "add_note", deal=deal["hs_deal_id"], text="a"), st("lyra", "create_task", deal=deal["hs_deal_id"], title="b")))
    await say(conn, deps(gw, w, s, llm), REP_A, "anota e cria tarefa")
    assert w.created == []


async def test_direct_address_routes_to_that_agent_only(world):  # noqa: F811
    conn, gw, w, s, _ = world
    out = await say(conn, deps(gw, w, s), REP_A, "Vega, como estou na meta?")
    assert out["body"].startswith("*Vega*:")
    out = await say(conn, deps(gw, w, s), REP_A, "Altair, como estou na meta?")   # not Altair's job
    assert out["body"].startswith("*Altair*:") and "Isso não é comigo" in out["body"] and "*Vega*" in out["body"]
    out = await say(conn, deps(gw, w, s), REP_A, "Argus")
    assert "Argus aqui" in out["body"]


async def test_addressed_agent_cannot_be_overridden_by_llm_plan(world):  # noqa: F811
    conn, gw, w, s, _ = world
    deal = await _own_deal(conn)
    llm = FakeLlm(tool=plan(st("lyra", "add_note", deal=deal["hs_deal_id"], text="x")))
    await say(conn, deps(gw, w, s, llm), REP_A, "Vega, faz uma nota aí")
    assert w.created == []


async def test_team_roster_and_nickname(world):  # noqa: F811
    conn, gw, w, s, _ = world
    out = await say(conn, deps(gw, w, s), REP_A, "quem está na equipe?")
    assert all(n in out["body"] for n in ("Orion", "Vega", "Altair", "Lyra", "Aurora", "Argus")) and out["body"].startswith("*Orion*:")
    out = await say(conn, deps(gw, w, s), REP_A, "me chama de Rê")
    assert "Rê" in out["body"]
    with conn.cursor() as cur:
        cur.execute("select display_name from app.app_user where phone_e164=%s", (REP_A,))
        assert cur.fetchone()["display_name"] == "Rê"


async def test_argus_data_quality_is_scoped_and_signed(world):  # noqa: F811
    conn, gw, w, s, _ = world
    out = await say(conn, deps(gw, w, s), REP_A, "posso confiar nos meus dados?")
    assert out["body"].startswith("*Argus*:") and "próximo passo" in out["body"]


async def test_morning_brief_is_aurora(world):  # noqa: F811
    conn, gw, w, s, _ = world
    out = await say(conn, deps(gw, w, s), REP_A, reply="act:open:brief")
    assert out["body"].startswith("*Aurora*:")


async def test_agent_activity_view(world):  # noqa: F811
    conn, gw, w, s, _ = world
    await say(conn, deps(gw, w, s), REP_A, "meu funil")
    with conn.cursor() as cur:
        cur.execute("select agent, steps, ok from serving.v_agent_activity")
        assert [(r["agent"], r["steps"], r["ok"]) for r in cur.fetchall()] == [("altair", 1, 1)]
