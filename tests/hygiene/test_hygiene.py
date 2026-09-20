"""Polaris, the Coach (ADR 0003): a read-only fix queue computed in code."""
from datetime import date

from omnidata.agents import team as T
from omnidata.hygiene.compute import Deal, fix_queue, name_ok
from omnidata.hygiene.spec import spec_json

from ..insights.test_insights import ask, ins  # noqa: F401  (fixture reuse)

TODAY = date(2026, 9, 20)


def deal(i, name="Acme [Marketplace]", amount=1000, owner="o1", active=True, close=date(2026, 12, 1), nxt=date(2026, 10, 1), notes=1):
    return Deal(str(i), name, amount, owner, active, close, nxt, notes)


def test_a_complete_deal_has_no_issue_and_each_gap_is_flagged():
    q = fix_queue([deal(1)], TODAY, is_manager=False)
    assert q["clean"] == 1 and q["issues"] == [] and q["queue"] == []
    bad = fix_queue([deal(1, amount=0, close=date(2026, 1, 1), nxt=None, notes=0, name="Acme")], TODAY, is_manager=False)
    assert {i["code"] for i in bad["issues"]} == {"no_amount", "close_date_past", "no_next_step", "no_notes", "name_format"}


def test_name_format_accepts_both_conventions_and_rejects_broken_brackets():
    assert name_ok("Cobli<>FIND [Inbound de NF's]") and name_ok("Acme – Renovação")
    assert not name_ok("Oriz [Diagnóstico de Dores") and not name_ok("Brasol<>FIND")


def test_a_gap_on_almost_everything_is_reported_as_systemic_and_not_blamed_on_every_deal():
    many = [deal(i, amount=0, nxt=None) for i in range(20)] + [deal(99, amount=500_000, nxt=None)]
    q = fix_queue(many, TODAY, is_manager=False, limit=5)
    assert "no_next_step" in q["systemic"]
    # R$0 deals are dropped from the bulk queue for the systemic gap; the valuable deal stays and comes first
    assert q["queue"][0]["id"] == "99" and q["queue"][0]["issues"] == ["no_next_step"]


def test_queue_is_ranked_by_value_and_owner_level_items_are_manager_only():
    ds = [deal(1, "A [X]", amount=100, notes=0), deal(2, "B [X]", amount=900, notes=0), deal(3, "C [X]", amount=500, active=False, notes=0),
          deal(4, name="Dup [X]", amount=50, notes=0), deal(5, name="dup [x]", amount=50, notes=0)]
    rep = fix_queue(ds, TODAY, is_manager=False)
    mgr = fix_queue(ds, TODAY, is_manager=True)
    assert [r["id"] for r in rep["queue"]][:3] == ["2", "3", "1"] and "manager" not in rep
    assert len(mgr["manager"]["owner_inactive"]) == 1 and mgr["manager"]["duplicates"] == [{"name": "Dup [X]", "deals": 2}]
    assert all(not set(r["issues"]) & {"owner_inactive", "duplicate"} for r in mgr["queue"])   # the seller is never asked to fix those


def test_polaris_is_read_only_and_only_lyra_writes():
    assert T.POLARIS.tools == ("get_fix_queue",) and not (set(T.POLARIS.tools) & T.WRITE_TOOLS)
    assert T.TOOL_OWNER["get_fix_queue"] == "polaris" and T.parse_address("Polaris, o que corrijo?")[0].key == "polaris"
    fix_tools = {i["tool"] for i in spec_json()["issues"] if i["tool"]}
    assert fix_tools <= {"add_note", "create_task", "propose_deal_update"} and all(T.TOOL_OWNER[t] == "lyra" for t in fix_tools)


async def test_polaris_answers_signed_with_the_queue_from_the_database(ins):  # noqa: F811
    out = await ask(ins, "o que preciso corrigir nos meus negócios?")
    assert out["body"].startswith("*Polaris*:") and "negócios abertos estão completos" in out["body"]
    wrong = await ask(ins, "Vega, o que preciso corrigir?")
    assert "Isso não é comigo" in wrong["body"] and "Polaris" in wrong["body"]
