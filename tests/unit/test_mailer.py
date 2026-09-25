"""GmailSender: SMTP is injected via smtp_factory so this never touches the network."""
import pytest

from omnidata.mailer.gmail import EmailError, GmailSender


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
