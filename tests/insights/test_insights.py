"""Company insights: extractors (pure), then the agents that own each insight (Lyra, Altair, Vega, Argus, Aurora, Orion)."""
import json
from pathlib import Path

import pytest

from omnidata.agents import team as T
from omnidata.agents.orion import validate_plan
from omnidata.datasets.importer import ImportOptions, import_file
from omnidata.datasets.parse import read_table
from omnidata.datasets.spec import DEALS
from omnidata.datasets.validate import validate
from omnidata.insights import compute as C
from omnidata.insights.spec import spec_json
from omnidata.llm.base import ToolCall

from ..datasets.test_datasets import DATA
from ..e2e.test_bot import deps, say
from ..fakes import FakeGateway, FakeLlm, FakeWriter
from ..helpers import add_user


def rec(i, name, status="open", notes=(), campaign=None, reason=None, amount=1000):
    return C.Rec(str(i), name, status, amount, campaign, reason, list(notes))


def fixture_recs():
    rep, rows = validate(DEALS, read_table(DATA, "x.csv"), "x.csv", DATA)
    return [C.Rec(r["id"], r["name"], r["status"], r["amount"], r["campaign"], r["lost_reason"], r["notes"]) for r in rows]


# ---------------- extractors ----------------
def test_pains_labelled_first_cues_only_without_label_and_deduped_per_deal():
    r = rec(1, "A – B", notes=["Discovery concluída. Dor validada: retrabalho entre times.", "Dor principal: retrabalho entre times",
                              "Cliente relatou dificuldade de integrar sistemas. Falta de visibilidade."])
    got = C.pains_of(r)
    assert got.count("retrabalho entre times") == 2 and any(p.startswith("dificuldade de integrar") for p in got)
    a = C.analyze([r, rec(2, "C – D", notes=["Dor validada: retrabalho entre times"])])
    assert a["pains"]["items"][0] == {**a["pains"]["items"][0], "pain": "retrabalho entre times", "deals": 2}   # one vote per deal


def test_systems_are_whole_words_with_roles_and_categories():
    r = rec(1, "A – B", status="won", notes=["Ganhamos contra Zoho: valor percebido.", "Roda Totvs Protheus há anos", "comprou sapato novo"])
    s = C.systems_of(r)
    assert set(s) == {"Zoho", "Totvs"} and s["Zoho"] == {"mention", "won_against"} and "SAP" not in s   # "sapato" is not SAP
    lost = rec(2, "C – D", status="lost", reason="Priorizou solução interna (RD Station)")
    assert C.systems_of(lost)["RD Station"] == {"mention", "internal"}
    an = C.analyze([r, lost])["systems"]
    assert {x["system"] for x in an["erp"]} == {"Totvs"} and {x["system"] for x in an["crm"]} == {"Zoho", "RD Station"}


def test_demand_type_and_segment_heuristics_are_guarded():
    assert C.demand_type("Girassol Clínicas – Portal do Cliente") == "Portal do Cliente" and C.demand_type("Só um nome") is None
    recs = [rec(i, f"Empresa{i} Clínicas – Piloto IA") for i in range(9)] + [rec(99, "Rara Coworking – Piloto IA")]
    seg = {s["key"]: s["deals"] for s in C.analyze(recs)["segments"]["items"]}
    assert seg == {"Clínicas": 9}          # "Coworking" repeats too little to be called a segment


@pytest.mark.parametrize("reason,code", [("Preço acima do orçamento aprovado", "price"), ("Projeto adiado para o próximo ano fiscal", "budget_timing"),
                                         ("Decisor saiu da empresa", "champion_lost"), ("Sem resposta após 3 tentativas de contato", "no_decision"),
                                         ("Escopo não aderente ao que precisavam", "product_fit"), ("Priorizou solução interna (Totvs)", "internal_solution"),
                                         ("Escolheram outra coisa qualquer", "other")])
def test_loss_reason_taxonomy(reason, code):
    assert C.classify_loss(reason)[0] == code


def test_terms_never_join_words_across_dropped_words_or_punctuation():
    recs = [rec(i, "A – B", notes=["Valor percebido em integração e suporte. Contrato assinado."]) for i in range(4)]
    t = C.terms(recs)
    phrases = {x["term"] for x in t["phrases"]}
    assert "valor percebido" not in phrases                     # both are stopwords by design
    assert "integração suporte" not in phrases and "percebido integração" not in phrases   # 'e' and 'em' sit between them
    assert "contrato assinado" in phrases and {x["term"] for x in t["words"]} >= {"integração", "suporte", "contrato"}
    assert all(x["deals"] == 4 for x in t["words"])             # counted by deal, not by repetition


def test_win_rate_association_needs_enough_closed_deals():
    recs = [rec(i, "A – B", status="won" if i % 2 else "lost", notes=["Desconto pontual pedido"]) for i in range(12)] + \
           [rec(100 + i, "A – B", notes=["Sinal raro aqui", "Sinal raro aqui"]) for i in range(3)]
    t = {x["term"]: x for x in C.terms(recs)["phrases"]}
    assert t["desconto pontual"]["win_rate"] == 0.5 and t["sinal raro"]["win_rate"] is None


def test_real_export_fixture_gives_the_expected_shape():
    a = C.analyze(fixture_recs(), 8)
    cov = a["coverage"]
    assert cov["deals"] == 63 and cov["with_demand_type"] == 1.0 and cov["lost_with_reason"] == 1.0
    assert a["pains"]["with_pain"] > 0 and {"pain", "deals", "share"} <= set(a["pains"]["items"][0])
    assert a["demand_types"]["items"] and a["systems"]["items"] and a["campaigns"]["items"]
    assert a["segments"]["items"] == []                         # 63 deals / 15 segments: none repeats 8 times, so none is invented
    assert sum(x["deals"] for x in a["loss_reasons"]["taxonomy"]) == cov["lost"]
    assert a["pains"]["low_n"] is True                          # under 20 mentions: only indicative


def test_empty_input_does_not_crash():
    a = C.analyze([])
    assert a["coverage"]["deals"] == 0 and a["pains"]["items"] == [] and a["terms"]["words"] == []


def test_spec_is_in_sync_with_the_web_copy_and_names_the_owners():
    web = json.loads((Path(__file__).parents[2] / "web/src/lib/insights-spec.json").read_text())
    assert web == json.loads(json.dumps(spec_json())), "run: uv run omnidata insights spec > web/src/lib/insights-spec.json"
    owners = web["owners"]
    assert {owners[k] for k in owners} <= set(T.SPECIALISTS)


# ---------------- who owns what (the distribution the whiteboard asked for) ----------------
def test_every_whiteboard_topic_has_exactly_one_owning_agent():
    assert T.TOOL_OWNER["get_pains"] == "lyra" and T.TOOL_OWNER["get_recurring_terms"] == "lyra"           # dores, termos recorrentes
    assert T.TOOL_OWNER["get_systems_landscape"] == "altair" and T.TOOL_OWNER["get_demand_types"] == "altair"  # ERPs, tipo de demanda
    assert T.TOOL_OWNER["get_segment_insights"] == "vega"                                                     # outros insights
    assert T.TOOL_OWNER["get_insight_coverage"] == "argus" and T.TOOL_OWNER["get_insight_digest"] == "aurora"


def test_insight_tools_are_read_only_so_a_plan_can_mix_them_freely():
    plan = validate_plan([{"agent": "lyra", "tool": "get_pains"}, {"agent": "altair", "tool": "get_systems_landscape", "args": {"category": "erp"}},
                          {"agent": "argus", "tool": "get_insight_coverage"}])
    assert plan and [s.agent for s in plan] == ["lyra", "altair", "argus"]
    assert validate_plan([{"agent": "vega", "tool": "get_pains"}]) is None            # Vega does not own dores
    assert validate_plan([{"agent": "altair", "tool": "get_systems_landscape", "args": {"category": "banana"}}]) is None


# ---------------- end to end through the bot ----------------
ADMIN = "+5511988880001"


@pytest.fixture
def ins(conn):
    import_file(conn, "deals", DATA, "d.csv", ImportOptions(dry_run=False))
    add_user(conn, ADMIN, "9990", role="admin", name="Gestor")
    with conn.cursor() as cur:
        cur.execute("select hs_owner_id, count(*) n from silver.deal where hs_owner_id like 'up:%' group by 1 order by n desc limit 2")
        top = cur.fetchall()
    add_user(conn, "+5511988880002", top[0]["hs_owner_id"], name="Rep A")
    add_user(conn, "+5511988880003", top[1]["hs_owner_id"], name="Rep B")
    return conn, FakeGateway(), FakeWriter(), top


async def ask(ins, text, llm=None, phone=ADMIN):
    conn, gw, w, _ = ins
    from omnidata.config import Settings
    return await say(conn, deps(gw, w, Settings(rate_limit_msgs_per_hour=1000), llm), phone, text)


async def test_each_agent_answers_its_own_insight_signed(ins):
    out = await ask(ins, "quais as dores mais citadas nas empresas?")
    assert out["body"].startswith("*Lyra*:") and "Dores mais citadas" in out["body"] and "negócios têm dor registrada" in out["body"]
    out = await ask(ins, "que tipos de demanda estão entrando?")
    assert out["body"].startswith("*Altair*:") and "Tipos de demanda" in out["body"] and "em aberto" in out["body"]
    out = await ask(ins, "quais ERPs aparecem nas contas?")
    assert out["body"].startswith("*Altair*:") and "Totvs" in out["body"] and "CRM/vendas" not in out["body"]   # ERPs only, not CRMs
    out = await ask(ins, "qual segmento converte mais?")
    assert out["body"].startswith("*Vega*:") and "Não identifiquei segmentos" in out["body"] and "campanha" in out["body"]   # says WHY it is empty
    out = await ask(ins, "qual campanha converte mais?")
    assert out["body"].startswith("*Vega*:") and "Campanhas por volume" in out["body"] and "ganho" in out["body"]
    out = await ask(ins, "quais os motivos de perda?")
    assert out["body"].startswith("*Vega*:") and "Motivos de perda" in out["body"]
    out = await ask(ins, "posso confiar nos insights? qual a cobertura?")
    assert out["body"].startswith("*Argus*:") and "Cobertura dos" in out["body"]
    out = await ask(ins, "qual o insight do dia?")
    assert out["body"].startswith("*Aurora*:") and "Insight do dia" in out["body"]
    out = await ask(ins, "quais termos mais se repetem nas notas?")
    assert out["body"].startswith("*Lyra*:") and "não a causa" in out["body"]           # correlation caveat is always shown


async def test_orion_splits_a_broad_insights_request_between_three_agents(ins):
    out = await ask(ins, "me dá os insights das empresas")
    b = out["body"]
    assert "*Lyra*:" in b and "*Altair*:" in b and "*Argus*:" in b
    assert b.index("*Lyra*") < b.index("*Altair*") < b.index("*Argus*") and out["type"] == "text"
    conn = ins[0]
    with conn.cursor() as cur:
        cur.execute("select agent, tool, status from app.agent_step order by step_no")
        assert [(r["agent"], r["tool"], r["status"]) for r in cur.fetchall()] == [
            ("lyra", "get_pains", "ok"), ("altair", "get_demand_types", "ok"), ("argus", "get_insight_coverage", "ok")]


async def test_addressing_the_wrong_agent_points_to_the_owner(ins):
    out = await ask(ins, "Vega, quais as dores mais citadas?")
    assert out["body"].startswith("*Vega*:") and "Isso não é comigo" in out["body"] and "Lyra" in out["body"]
    out = await ask(ins, "Lyra, quais as dores mais citadas?")
    assert out["body"].startswith("*Lyra*:") and "Dores mais citadas" in out["body"]


async def test_llm_plan_mixing_agents_runs_and_is_validated(ins):
    plan = ToolCall("plan", {"steps": [{"agent": "altair", "tool": "get_systems_landscape", "args": {"category": "erp"}},
                                        {"agent": "lyra", "tool": "get_pains", "args": {"limit": 3}}]})
    out = await ask(ins, "compara os ERPs e as dores", llm=FakeLlm(tool=plan))
    assert "*Altair*:" in out["body"] and "*Lyra*:" in out["body"] and "Totvs" in out["body"]
    bad = ToolCall("plan", {"steps": [{"agent": "vega", "tool": "get_pains"}]})               # not Vega's tool: rejected, keyword route answers
    out = await ask(ins, "quais as dores?", llm=FakeLlm(tool=bad))
    assert out["body"].startswith("*Lyra*:")


async def test_number_guard_covers_insight_narration(ins):
    llm = FakeLlm(tool=ToolCall("get_pains", {}), narration="Foram 9.999 negócios com dor de churn.")
    out = await ask(ins, "dores?", llm=llm)
    assert "9.999" not in out["body"] and "Dores mais citadas" in out["body"]


async def test_insights_are_scoped_to_what_the_person_can_see(ins):
    conn, gw, w, top = ins
    total = (await ask(ins, "posso confiar nos insights? cobertura"))["body"]
    a = (await ask(ins, "posso confiar nos insights? cobertura", phone="+5511988880002"))["body"]
    b = (await ask(ins, "posso confiar nos insights? cobertura", phone="+5511988880003"))["body"]
    num = lambda s: int(s.split("Cobertura dos ")[1].split(" ")[0])  # noqa: E731
    assert num(total) == 63 and num(a) == top[0]["n"] and num(b) == top[1]["n"] and num(a) + num(b) < num(total)


async def test_empty_data_gives_an_honest_answer_not_zeroes(conn):
    add_user(conn, ADMIN, "9990", role="admin")
    from omnidata.config import Settings
    out = await say(conn, deps(FakeGateway(), FakeWriter(), Settings(rate_limit_msgs_per_hour=1000)), ADMIN, "quais as dores?")
    assert "Ainda não tenho dados suficientes" in out["body"]


def test_hubspot_corporate_naming_and_mentions_ignored():
    """Real export: 'Cliente<>Parceiro [Demanda]', notes with @mentions of colleagues."""
    from omnidata.insights.compute import Rec, company, demand_type, terms
    assert demand_type("Cobli<>FIND [Inbound de NF's]") == "Inbound de NF's"
    assert demand_type("Brasol<>FIND ") is None  # no brackets, no separator: not invented
    assert company("Cobli<>FIND [Inbound de NF's]") == "Cobli"
    recs = [Rec(id=str(i), name="A<>B [X]", status="open", notes=["Aguardando retorno. @Thaís Carneiro @Rafael Almeida"]) for i in range(4)]
    words = {t["term"] for t in terms(recs)["words"]}
    assert "thaís" not in words and "carneiro" not in words and "aguardando" in words
