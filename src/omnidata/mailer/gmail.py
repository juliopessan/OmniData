"""Outbound e-mail via a single company Gmail account (Vela, D-proposal). SMTP + app password — the same
simplicity level as every other integration here (a flat secret in .env, no OAuth flow) rather than the Gmail
API's OAuth2 dance. If Workspace admin policy blocks app passwords, swap the internals for OAuth2/XOAUTH2 without
changing this class's public `send()` — callers never see the transport."""
from __future__ import annotations

import asyncio
import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

SmtpFactory = Callable[[], Any]  # () -> a context-manager SMTP-like object (real smtplib.SMTP or a test double)


class EmailError(RuntimeError):
    pass


class GmailSender:
    def __init__(self, user: str, app_password: str, from_name: str = "OmniData",
                 smtp_factory: SmtpFactory | None = None) -> None:
        self._user, self._password, self._from_name = user, app_password, from_name
        self._smtp_factory = smtp_factory or (lambda: smtplib.SMTP("smtp.gmail.com", 587, timeout=20))

    async def send(self, to: str, subject: str, body: str, attachment: tuple[str, bytes, str] | None = None) -> None:
        msg = EmailMessage()
        msg["From"] = f"{self._from_name} <{self._user}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if attachment:
            filename, data, mime = attachment
            maintype, _, subtype = mime.partition("/")
            msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)
        await asyncio.to_thread(self._send_sync, msg)

    def _send_sync(self, msg: EmailMessage) -> None:
        try:
            with self._smtp_factory() as s:
                s.starttls()
                s.login(self._user, self._password)
                s.send_message(msg)
        except smtplib.SMTPException as exc:
            raise EmailError(str(exc)) from exc
