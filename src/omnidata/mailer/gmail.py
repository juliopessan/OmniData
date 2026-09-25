"""Outbound e-mail via a single company Gmail account (Vela, D-proposal). Two senders behind the same `EmailSender`
interface, chosen in jobs/worker.py::build_emailer by whichever credentials are configured:
  GmailApiSender  Gmail API + OAuth2 (refresh token), no SMTP at all — needed when SMTP/app passwords are blocked
                  by Workspace admin policy. Only httpx (already a dependency) — no google-api-python-client.
  GmailSmtpSender SMTP + app password — the simpler path when app passwords are allowed on the account.
Both build the same RFC 2822 message via the stdlib `email` module; callers never see which transport is behind
`send()`."""
from __future__ import annotations

import asyncio
import base64
import smtplib
import time
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any, Protocol

import httpx

SmtpFactory = Callable[[], Any]  # () -> a context-manager SMTP-like object (real smtplib.SMTP or a test double)
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class EmailError(RuntimeError):
    pass


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, body: str, attachment: tuple[str, bytes, str] | None = None) -> None: ...


def _build_message(to: str, subject: str, body: str, attachment: tuple[str, bytes, str] | None,
                   from_header: str | None) -> EmailMessage:
    msg = EmailMessage()
    if from_header:
        msg["From"] = from_header
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment:
        filename, data, mime = attachment
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)
    return msg


class GmailApiSender:
    """Gmail API `users.messages.send` with an OAuth2 refresh token (no SMTP, no app password). The refresh token
    is obtained once via `scripts/gmail_oauth_setup.py` (interactive consent in the user's own browser) and then
    stored as GMAIL_REFRESH_TOKEN — this class only ever exchanges it for short-lived access tokens."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, user: str = "", from_name: str = "OmniData",
                 http: httpx.AsyncClient | None = None) -> None:
        self._client_id, self._client_secret, self._refresh_token = client_id, client_secret, refresh_token
        self._user, self._from_name = user, from_name
        self._http = http or httpx.AsyncClient(timeout=20.0)
        self._token: str | None = None
        self._expires_at = 0.0

    async def _access_token(self) -> str:
        if self._token and time.time() < self._expires_at - 30:
            return self._token
        try:
            r = await self._http.post(TOKEN_URL, data={"client_id": self._client_id, "client_secret": self._client_secret,
                                                        "refresh_token": self._refresh_token, "grant_type": "refresh_token"})
        except httpx.TransportError as exc:
            raise EmailError(f"gmail oauth transport: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise EmailError(f"gmail oauth refresh {r.status_code}: {r.text[:200]}")
        d = r.json()
        self._token = str(d["access_token"])
        self._expires_at = time.time() + float(d.get("expires_in", 3600))
        return self._token

    async def send(self, to: str, subject: str, body: str, attachment: tuple[str, bytes, str] | None = None) -> None:
        from_header = f"{self._from_name} <{self._user}>" if self._user else None
        msg = _build_message(to, subject, body, attachment, from_header)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        token = await self._access_token()
        try:
            r = await self._http.post(SEND_URL, headers={"Authorization": f"Bearer {token}"}, json={"raw": raw})
        except httpx.TransportError as exc:
            raise EmailError(f"gmail api transport: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise EmailError(f"gmail api {r.status_code}: {r.text[:200]}")


class GmailSmtpSender:
    def __init__(self, user: str, app_password: str, from_name: str = "OmniData",
                 smtp_factory: SmtpFactory | None = None) -> None:
        self._user, self._password, self._from_name = user, app_password, from_name
        self._smtp_factory = smtp_factory or (lambda: smtplib.SMTP("smtp.gmail.com", 587, timeout=20))

    async def send(self, to: str, subject: str, body: str, attachment: tuple[str, bytes, str] | None = None) -> None:
        msg = _build_message(to, subject, body, attachment, f"{self._from_name} <{self._user}>")
        await asyncio.to_thread(self._send_sync, msg)

    def _send_sync(self, msg: EmailMessage) -> None:
        try:
            with self._smtp_factory() as s:
                s.starttls()
                s.login(self._user, self._password)
                s.send_message(msg)
        except smtplib.SMTPException as exc:
            raise EmailError(str(exc)) from exc


# Back-compat alias: existing call sites/tests import GmailSender expecting the SMTP path.
GmailSender = GmailSmtpSender
