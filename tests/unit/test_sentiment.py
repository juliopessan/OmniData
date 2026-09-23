from omnidata.bot.sentiment import classify


def test_pure_acknowledgement_is_reactable():
    for t in ("valeu", "Valeu!", "obrigado", "obrigada!", "blz", "beleza", "show", "top", "ok", "👍"):
        assert classify(t).acknowledgement, t


def test_acknowledgement_with_more_content_is_not_reactable():
    assert not classify("valeu, mas ainda preciso de ajuda com a Acme").acknowledgement
    assert not classify("obrigado! quanto falta pra bater a meta?").acknowledgement


def test_negative_keywords():
    assert classify("isso está péssimo, nunca mais uso").negative
    assert classify("o sistema não está funcionando").negative
    assert not classify("o cliente disse que o produto é ótimo").negative


def test_urgent_keywords():
    assert classify("preciso disso urgente").urgent
    assert classify("me responde agora mesmo por favor").urgent
    assert not classify("posso ver isso mais tarde").urgent


def test_plain_question_triggers_nothing():
    s = classify("como estou na meta desse mês?")
    assert not s.acknowledgement and not s.negative and not s.urgent
