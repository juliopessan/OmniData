"""GmailSender: SMTP is injected via smtp_factory so this never touches the network."""
import base64
import json
from email import message_from_bytes, policy

import httpx
import pytest

from omnidata.mailer.gmail import EmailError, GmailApiSender, GmailSender


class FakeSmtp:
    sent: list = []
    logged_in: list = []

    def __init__(self):
        FakeSmtp.sent = []
        FakeSmtp.logged_in = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        FakeSmtp.logged_in.append((user, password))

    def send_message(self, msg):
        FakeSmtp.sent.append(msg)


class FailingSmtp(FakeSmtp):
    def send_message(self, msg):
        import smtplib
        raise smtplib.SMTPException("boom")


async def test_send_includes_attachment_and_recipient():
    sender = GmailSender("vendas@empresa.com", "app-pass", smtp_factory=FakeSmtp)
    await sender.send("cliente@acme.com", "Proposta — Acme", "Segue em anexo.",
                       attachment=("proposta.pdf", b"%PDF-fake", "application/pdf"))
    assert len(FakeSmtp.sent) == 1
    msg = FakeSmtp.sent[0]
    assert msg["To"] == "cliente@acme.com"
    assert msg["Subject"] == "Proposta — Acme"
    attachments = list(msg.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "proposta.pdf"
    assert FakeSmtp.logged_in == [("vendas@empresa.com", "app-pass")]


async def test_send_without_attachment():
    sender = GmailSender("vendas@empresa.com", "app-pass", smtp_factory=FakeSmtp)
    await sender.send("cliente@acme.com", "Oi", "Corpo simples")
    assert len(FakeSmtp.sent) == 1
    assert not list(FakeSmtp.sent[0].iter_attachments())


async def test_send_wraps_smtp_errors():
    sender = GmailSender("vendas@empresa.com", "app-pass", smtp_factory=FailingSmtp)
    with pytest.raises(EmailError):
        await sender.send("cliente@acme.com", "Oi", "Corpo")


def _api_sender(handler):
    return GmailApiSender("cid", "csecret", "rtoken", "vendas@empresa.com", "Vela",
                          http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_gmail_api_refreshes_token_then_sends_raw_message():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600})
        assert request.headers["authorization"] == "Bearer tok-123"
        body = json.loads(request.content)
        raw = base64.urlsafe_b64decode(body["raw"] + "==")
        parsed = message_from_bytes(raw, policy=policy.default)
        assert parsed["To"] == "cliente@acme.com"
        attachments = list(parsed.iter_attachments())
        assert len(attachments) == 1 and attachments[0].get_payload(decode=True) == b"%PDF-fake"
        return httpx.Response(200, json={"id": "msg-1"})

    sender = _api_sender(handler)
    await sender.send("cliente@acme.com", "Proposta", "Segue em anexo.", attachment=("p.pdf", b"%PDF-fake", "application/pdf"))
    assert len(calls) == 2 and calls[0].url.path == "/token" and calls[1].url.path.endswith("/messages/send")


async def test_gmail_api_reuses_token_until_near_expiry():
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/token":
            token_calls += 1
            return httpx.Response(200, json={"access_token": f"tok-{token_calls}", "expires_in": 3600})
        return httpx.Response(200, json={"id": "msg-1"})

    sender = _api_sender(handler)
    await sender.send("a@acme.com", "Oi", "Corpo")
    await sender.send("a@acme.com", "Oi de novo", "Corpo")
    assert token_calls == 1  # segundo envio reaproveitou o access_token ainda válido


async def test_gmail_api_wraps_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(403, text="insufficient scope")

    sender = _api_sender(handler)
    with pytest.raises(EmailError):
        await sender.send("cliente@acme.com", "Oi", "Corpo")
