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
