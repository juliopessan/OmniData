"""Bugs found by reading a real conversation: hour-blind greeting, technical-term leak, and the new deterministic
follow-up suggestions (never LLM-invented, always conditioned on a real signal in the payload)."""
from omnidata.bot import strings_ptbr as S


def test_brief_greeting_follows_the_hour():
    assert S.tpl_brief({"hour": 8, "quota": {}, "attention": {"deals": []}}).startswith("Bom dia")
    assert S.tpl_brief({"hour": 14, "quota": {}, "attention": {"deals": []}}).startswith("Boa tarde")
    assert S.tpl_brief({"hour": 20, "quota": {}, "attention": {"deals": []}}).startswith("Boa noite")
    assert S.tpl_brief({"quota": {}, "attention": {"deals": []}}).startswith("Bom dia")  # no hour given: same as before


def test_attention_suggests_fix_queue_only_when_flagged():
    d = {"deals": [{"name": "Acme", "amount": 1000, "flags": []}]}
    assert "Polaris" not in S.tpl_attention(d)
    d["suggest_fix_queue"] = True
    assert "Polaris" in S.tpl_attention(d)


def test_playbook_objection_always_suggests_a_note_when_there_is_data():
    out = S.tpl_playbook({"topic": "objection", "lost": 5, "items": [{"label": "preço", "deals": 3}]})
    assert "Lyra" in out
    assert S.tpl_playbook({"topic": "objection", "items": []}) == S.NO_INSIGHT  # no data: no suggestion either


def test_evening_recap_reports_only_what_actually_happened():
    empty = S.tpl_evening_recap({"name": "Ana", "won_count": 0, "won_amount": 0, "notes_count": 0, "tomorrow": []})
    assert "nenhum negócio fechado" in empty and "Amanhã" not in empty

    busy = S.tpl_evening_recap({"name": "Ana", "won_count": 2, "won_amount": 15000, "notes_count": 3,
                                "tomorrow": [{"name": "Beta Log"}, {"name": "Gamma Corp"}]})
    assert "fechou 2 negócio" in busy and "R$ 15.000" in busy and "registrou 3 nota" in busy
    assert "Beta Log" in busy and "Gamma Corp" in busy
