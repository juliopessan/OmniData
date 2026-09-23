"""Harness rules that live in code, not prompts (ADR 0003)."""
import json
from pathlib import Path

from omnidata.agents import team as T
from omnidata.agents.orion import plan_schema, validate_plan


def step(agent, tool, **args):
    return {"agent": agent, "tool": tool, "args": args}


def test_every_tool_has_exactly_one_owner_and_orion_owns_none():
    from omnidata.bot.tools.catalog import TOOLS
    assert set(T.TOOL_OWNER) == set(TOOLS)
    assert T.ORION.tools == () and "orion" not in T.SPECIALISTS
    assert len({a.name for a in T.TEAM.values()}) == len(T.TEAM) == 8


def test_valid_multi_step_plan_read_then_write():
    plan = validate_plan([step("vega", "get_quota_status"), step("lyra", "add_note", deal="Acme", text="oi")])
    assert plan and [s.agent for s in plan] == ["vega", "lyra"]


def test_plan_rejections():
    assert validate_plan([step("vega", "add_note", deal="Acme", text="x")]) is None          # tool not in Vega's allowlist
    assert validate_plan([step("orion", "get_kpis")]) is None and validate_plan([step("ghost", "get_kpis")]) is None
    assert validate_plan([step("vega", "get_kpis")] * 4) is None                              # > 3 steps
    assert validate_plan([]) is None and validate_plan("x") is None
    two_writes = [step("lyra", "add_note", deal="A1", text="x"), step("lyra", "create_task", deal="A1", title="t")]
    assert validate_plan(two_writes) is None                                                  # at most one write
    assert validate_plan([step("lyra", "add_note", deal="A1", text="x"), step("vega", "get_kpis")]) is None  # write must be last
    assert validate_plan([step("vega", "get_kpis", period="next_year")]) is None              # pydantic enum


def test_addressed_agent_restricts_plan():
    assert validate_plan([step("altair", "get_pipeline_summary")], forced=T.VEGA) is None
    assert validate_plan([step("vega", "get_kpis")], forced=T.VEGA)


def test_owner_scope_never_comes_from_the_plan():
    plan = validate_plan([step("vega", "get_kpis", owner_id="9001", hs_owner_id="9001")])
    assert plan and "owner_id" not in plan[0].args and "hs_owner_id" not in plan[0].args


def test_parse_address_assessor_style():
    a, rest = T.parse_address("Vega, como estou na meta?")
    assert a.key == "vega" and rest == "como estou na meta?"
    assert T.parse_address("@Lyra nota na Acme")[0].key == "lyra"
    assert T.parse_address("Aurora")[1] == ""
    assert T.parse_address("veganismo é bom") is None and T.parse_address("como estou") is None


def test_plan_schema_is_closed_over_the_team():
    sch = plan_schema()["parameters"]["properties"]["steps"]
    assert sch["maxItems"] == 3 and set(sch["items"]["properties"]["agent"]["enum"]) == set(T.SPECIALISTS)


def test_web_team_json_is_in_sync_with_python():  # single source of truth for the UI
    web = json.loads((Path(__file__).parents[2] / "web/src/lib/team.json").read_text())
    assert web == json.loads(json.dumps(T.export())), "run: uv run omnidata team export > web/src/lib/team.json"
