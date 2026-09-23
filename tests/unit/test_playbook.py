"""Nova (Coach de Vendas): tpl_playbook only narrates what insight_analysis already computed — no invented advice."""
from omnidata.agents.team import TOOL_OWNER
from omnidata.bot import strings_ptbr as S
from omnidata.bot.tools import catalog


def test_get_playbook_is_owned_by_nova_and_validates():
    assert TOOL_OWNER["get_playbook"] == "nova"
    parsed = catalog.validate("get_playbook", {"topic": "pain", "limit": 3})
    assert parsed is not None and parsed.model_dump() == {"topic": "pain", "limit": 3}
    assert catalog.validate("get_playbook", {"topic": "not_a_topic"}) is None


def test_objection_topic_lists_real_loss_reasons():
    d = {"topic": "objection", "lost": 12, "items": [{"label": "preço", "deals": 5}, {"label": "concorrente", "deals": 3}]}
    out = S.tpl_playbook(d)
    assert "12 negócios perdidos" in out and "preço: 5" in out and "concorrente: 3" in out


def test_pain_topic_flags_low_sample():
    d = {"topic": "pain", "with_pain": 2, "low_n": True, "items": [{"pain": "integração lenta", "deals": 2}]}
    out = S.tpl_playbook(d)
    assert "integração lenta (2)" in out and "Amostra pequena" in out


def test_pitch_topic_combines_demand_and_phrases():
    d = {"topic": "pitch", "demand": [{"key": "integração", "deals": 4}], "phrases": [{"term": "contrato assinado", "deals": 2}]}
    out = S.tpl_playbook(d)
    assert "integração (4)" in out and "contrato assinado (2)" in out


def test_no_data_never_invents_anything():
    assert S.tpl_playbook({"topic": "objection", "items": []}) == S.NO_INSIGHT
    assert S.tpl_playbook({"topic": "pain", "items": []}) == S.NO_INSIGHT
    assert S.tpl_playbook({"topic": "pitch", "demand": [], "phrases": []}) == S.NO_INSIGHT
