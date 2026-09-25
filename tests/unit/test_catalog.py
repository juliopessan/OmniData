from omnidata.bot.tools.catalog import SendProposal, validate


def test_send_proposal_whatsapp_only_does_not_require_email():
    v = validate(
        "send_proposal",
        {"deal": "Acme", "summary": "Escopo combinado em texto livre.", "channel": "whatsapp"},
    )
    assert isinstance(v, SendProposal)
    assert v.recipient_email == ""


def test_send_proposal_email_channel_requires_recipient_email():
    assert (
        validate(
            "send_proposal",
            {"deal": "Acme", "summary": "Escopo combinado em texto livre.", "channel": "email"},
        )
        is None
    )


def test_send_proposal_both_channel_requires_recipient_email():
    assert (
        validate(
            "send_proposal",
            {"deal": "Acme", "summary": "Escopo combinado em texto livre.", "channel": "both"},
        )
        is None
    )


def test_send_proposal_email_channel_with_recipient_email_validates():
    v = validate(
        "send_proposal",
        {
            "deal": "Acme",
            "summary": "Escopo combinado em texto livre.",
            "channel": "email",
            "recipient_email": "cliente@acme.com",
        },
    )
    assert isinstance(v, SendProposal)
    assert v.recipient_email == "cliente@acme.com"


def test_send_proposal_needs_only_the_deal():  # scope is optional: no scope = PDF with CRM data only
    v = validate("send_proposal", {"deal": "Empresa 890", "channel": "whatsapp"})
    assert isinstance(v, SendProposal) and v.summary == ""


def test_deal_query_tokens_drop_the_amount_and_punctuation():
    from omnidata.bot.repo import deal_query_tokens, normalize_deal_name
    assert deal_query_tokens("Empresa 890 – Novo (R$ 120.000)") == ["Empresa", "890", "Novo"]
    assert deal_query_tokens("Acme, R$ 5.000,00") == ["Acme"]
    assert normalize_deal_name("Empresa 890 – Novo (R$ 120.000)") == normalize_deal_name("Empresa 890 - Novo")
