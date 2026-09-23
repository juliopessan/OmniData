import pytest

from omnidata.bot.evolution import verify_evolution_secret
from omnidata.bot.router import keyword_route
from omnidata.bot.tools import catalog
from omnidata.llm.guard import numbers_ok
from omnidata.security.pii_masking import mask_pii


def test_pii_masking_covers_email_phone_cpf_cnpj():
    t = mask_pii("fale com joao@acme.com.br ou (11) 98888-7777, CPF 123.456.789-09, CNPJ 12.345.678/0001-95")
    assert "@" not in t and "98888" not in t and "123.456" not in t and "0001" not in t
    assert all(x in t for x in ("[EMAIL]", "[TEL]", "[CPF]", "[CNPJ]"))


def test_number_guard_accepts_faithful_and_rounded_numbers():  # §11.3
    data = {"attainment": 0.9775, "won_amount": 391000, "gap": 9000, "n_closed": 12, "win_rate": 0.58333}
    assert numbers_ok("Você está em 97,8% da meta; ganho R$ 391.000, faltam R$ 9.000. 12 negócios.", data)
    assert numbers_ok("Win rate de 58,3%.", data) and numbers_ok("Win rate de 58%.", data)


@pytest.mark.parametrize("bad", ["Você está em 96% da meta", "Faltam R$ 12.000", "São 13 negócios fechados", "Win rate de 61,0%",
                                 "Ganho de R$ 391.500", "Cobertura de 3,2x"])
def test_number_guard_catches_invented_numbers(bad):  # must catch 100% of invented numbers
    data = {"attainment": 0.9775, "won_amount": 391000, "gap": 9000, "n_closed": 12, "win_rate": 0.58333}
    assert not numbers_ok(bad, data)


def test_evolution_webhook_secret_verification():  # ADR 0008: no native signature, a shared header instead
    assert verify_evolution_secret("secret", "secret")
    assert not verify_evolution_secret("secret", "secret ")
    assert not verify_evolution_secret("secret", None) and not verify_evolution_secret("", "secret")


def test_model_can_never_supply_owner_scope():  # rule 7
    v = catalog.validate("get_kpis", {"period": "this_month", "owner_id": "9001", "hs_owner_id": "9001"})
    assert v is not None and "owner_id" not in v.model_dump()
    assert catalog.validate("drop_tables", {}) is None
    assert catalog.validate("propose_deal_update", {"deal": "Acme", "field": "owner", "value": "x"}) is None  # closed enum


def test_tool_schemas_are_valid_function_specs():
    for s in catalog.schemas():
        assert s["name"] and s["parameters"]["type"] == "object"


def test_keyword_router_top_intents():
    assert keyword_route("Como estou na META?") == "get_quota_status"
    assert keyword_route("meu funil") == "get_pipeline_summary"
    assert keyword_route("o que preciso fazer, quais negócios parados") == "list_deals_needing_action"
    assert keyword_route("blá blá") is None


def test_quota_template_never_prints_none():
    from omnidata.bot import strings_ptbr as S
    out = S.tpl_quota({"quota_amount": 100000, "attainment": 0.0, "won_amount": 0, "gap": 100000, "coverage": 1.5, "required_coverage": None})
    assert "None" not in out and "1,5x" in out
    assert "None" not in S.tpl_quota({"quota_amount": None})
