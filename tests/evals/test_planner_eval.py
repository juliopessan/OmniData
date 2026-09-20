"""Planner evaluation (golden set + held-out set) and the routing guarantees it protects."""
import asyncio
from pathlib import Path

from typer.testing import CliRunner

from omnidata.agents import team as T
from omnidata.agents.orion import validate_plan
from omnidata.bot.router import keyword_route
from omnidata.cli import app
from omnidata.evals import planner as ev
from omnidata.llm.base import RouterResult, ToolCall, Usage

HOLDOUT = Path(ev.__file__).with_name("planner_holdout.yaml")


def test_every_case_is_well_formed_and_its_ideal_plan_is_valid():
    for path in (ev.CASES_FILE, HOLDOUT):
        cases = ev.load_cases(path)
        assert len(cases) >= 16
        for c in cases:
            if c.kind == "plan":
                raw = [{"agent": a, "tool": t, "args": {"query": "acme"} if t == "get_deal" else {"deal": "Acme", "text": "x", "title": "t", "field": "amount", "value": "1"}}
                       for a, t in c.plan]
                assert c.plan and all(a in T.SPECIALISTS for a, _ in c.plan), c.id
                assert len(c.plan) <= T.MAX_STEPS and [t for _, t in c.plan if t in T.WRITE_TOOLS].__len__() <= 1, c.id
                if not any(t in T.WRITE_TOOLS for _, t in c.plan):
                    assert validate_plan(raw) is not None, c.id              # the ideal read-only plan passes Orion's own validation
            else:
                assert not c.plan, c.id
    ids = [c.id for c in ev.load_cases()] + [c.id for c in ev.load_cases(HOLDOUT)]
    assert len(ids) == len(set(ids))                                         # a phrase moved out of the held-out set must not stay in it


# Held-out phrases the keyword route is known to answer with a neighbouring read (documented, not tuned for: see planner_holdout.yaml).
KNOWN_WRONG = {"ho-18"}    # "será que a gente fecha a meta do trimestre?" -> quota status instead of the forecast


def test_keyword_mode_never_writes_and_never_gives_a_new_wrong_answer():
    """Safety floor for the degraded route: an unknown phrase falls back to the menu; never a write, never a NEW wrong answer."""
    for path, floor in ((ev.CASES_FILE, 0.8), (HOLDOUT, 0.0)):
        rep = ev.run_keyword(ev.load_cases(path))
        assert rep.count("critical") == 0
        wrong = {r.case.id for r in rep.results if r.outcome == "wrong"}
        assert wrong <= KNOWN_WRONG, [(r.case.id, r.got) for r in rep.results if r.outcome == "wrong" and r.case.id not in KNOWN_WRONG]
        assert rep.rate("correct") >= floor


def test_judge_outcomes():
    c = ev.Case("x", "t", "q", plan=(("vega", "get_kpis"),))
    w = ev.Case("w", "t", "q", plan=(("lyra", "add_note"),), menu_ok=True)
    multi = ev.Case("m", "t", "q", plan=(("aurora", "get_morning_brief"), ("polaris", "get_fix_queue")), menu_ok=True)
    assert ev.judge(c, "plan", (("vega", "get_kpis"),)) == "correct"
    assert ev.judge(c, "plan", (("vega", "get_quota_status"),)) == "wrong"          # another answer is worse than a menu
    assert ev.judge(c, "menu", ()) == "miss" and ev.judge(w, "menu", ()) == "acceptable"
    assert ev.judge(c, "plan", (("lyra", "add_note"),)) == "critical"               # a write nobody asked for
    assert ev.judge(multi, "plan", (("polaris", "get_fix_queue"),)) == "partial"
    assert ev.judge(c, "plan", (("vega", "get_kpis"), ("argus", "get_data_quality"))) == "extra"     # right step plus an unrequested read
    assert ev.judge(c, "plan", (("vega", "get_kpis"), ("lyra", "add_note"))) == "critical"          # ...but never plus a write
    assert ev.judge(ev.Case("o", "t", "q", kind="oos"), "plan", (("vega", "get_kpis"),)) == "wrong"
    assert ev.judge(ev.Case("o", "t", "q", kind="oos"), "oos", ()) == "correct"


class ScriptedLlm:
    """Answers each phrase with the ideal plan, or a broken one when told to."""
    def __init__(self, mode="ideal"):
        self.mode, self.cases = mode, {c.text: c for c in ev.load_cases()}

    async def route(self, system, user_text, tools):
        c = next((c for c in self.cases.values() if user_text in c.text or c.text.endswith(user_text)), None)
        if c is None or c.kind == "oos":
            return RouterResult(None, "FORA_DO_ESCOPO", Usage("fake", "fake"))
        steps = [{"agent": a, "tool": t, "args": {"query": "acme"} if t == "get_deal" else {"deal": "Acme", "text": "x", "title": "t", "field": "amount", "value": "1"}}
                 for a, t in c.plan]
        if self.mode == "extra_write":
            steps = (steps + [{"agent": "lyra", "tool": "add_note", "args": {"deal": "Acme", "text": "x"}}])[:3]
        if self.mode == "bad_agent":
            steps = [{"agent": "vega", "tool": "get_pains", "args": {}}]        # not in Vega's allowlist: Orion rejects it
        return RouterResult(ToolCall("plan", {"steps": steps}), None, Usage("fake", "fake"))

    async def narrate(self, system, payload_json):  # pragma: no cover
        raise AssertionError("not used")


def test_llm_mode_scores_an_ideal_planner_and_flags_a_bad_one():
    cases = [c for c in ev.load_cases() if c.tag not in ("enderecamento", "equipe")]
    ideal = asyncio.run(ev.run_llm(cases, ScriptedLlm()))
    assert ideal.rate("correct") == 1.0 and ideal.count("critical") == 0
    extra = asyncio.run(ev.run_llm(cases, ScriptedLlm("extra_write")))
    assert extra.count("critical") > 0                                          # an invented write is caught by the eval
    bad = asyncio.run(ev.run_llm(cases, ScriptedLlm("bad_agent")))
    # The invalid plan is rejected by code (never executed) and, exactly like the bot, the keyword route answers instead.
    assert bad.count("critical") == 0 and sum(1 for r in bad.results if r.got.startswith("rejected")) > 0


def test_routing_regressions_found_by_the_eval():
    assert keyword_route("mostra as metas do time") == "get_quota_status"        # plural
    assert keyword_route("qual foi o resultado do jogo?") is None                # 'resultado' alone is not the seller's KPIs
    assert keyword_route("me fala do negócio da Fast Shop") == "get_deal"
    assert keyword_route("deixa uma observação no deal da Bancorbrás: cliente quer revisar o SLA") is None   # a statement is not a lookup
    assert keyword_route("como está meu funil?") == "get_pipeline_summary"       # 'como está o ...' must not become a deal lookup


def test_cli_exit_codes_and_no_llm_message():
    r = CliRunner()
    assert r.invoke(app, ["eval", "planner"]).exit_code == 0
    assert r.invoke(app, ["eval", "planner", "--min-correct", "0.999"]).exit_code == 1
    out = r.invoke(app, ["eval", "planner", "--mode", "llm"], env={"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": ""})
    assert out.exit_code == 2
    assert r.invoke(app, ["eval", "planner", "--mode", "nope"]).exit_code == 2


def test_planner_prompt_describes_every_tool_and_asks_for_few_steps():
    """The first LLM run showed 'bom dia' and 'qual campanha converte mais?' called out of scope and get_deal rejected (no query):
    the prompt must carry tool descriptions and required args, and ask for the fewest steps."""
    from omnidata.agents.orion import ORION_SYSTEM
    from omnidata.bot.tools.catalog import TOOLS
    assert all(t in ORION_SYSTEM for t in TOOLS) and "get_deal(query)" in ORION_SYSTEM and "MENOR número de passos" in ORION_SYSTEM
    assert all(desc in ORION_SYSTEM for _, desc in TOOLS.values())
