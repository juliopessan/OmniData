"""Runs BEFORE the request body is read. FastAPI parses a form body before it resolves dependencies, so a token check inside the
route came too late: an unauthenticated client could make the server receive and spool a huge upload before it answered 401.
Here the admin token and the size limits are enforced first; the route-level check stays as a second layer."""
from __future__ import annotations

import hmac
import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..config import get_settings

MULTIPART_OVERHEAD = 200_000   # form fields and boundaries around the file, on top of dataset_max_bytes
GUARDED_METHODS = {"POST", "PUT", "PATCH"}


def admin_check(authorization: str | None) -> tuple[int, str] | None:
    """None when the bearer token is valid; otherwise (status, message). Constant-time comparison."""
    token = get_settings().admin_api_token
    if not token:
        return 503, "uploads disabled: ADMIN_API_TOKEN is not configured"
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not supplied or not hmac.compare_digest(supplied.encode(), token.encode()):
        return 401, "invalid token"
    return None


async def _reply(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    headers: list[tuple[bytes, bytes]] = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if status == 401:
        headers.append((b"www-authenticate", b"Bearer"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class BodyGuardMiddleware:
    """Pure ASGI middleware (no BaseHTTPMiddleware: it must not touch the body stream)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in GUARDED_METHODS:
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        headers: dict[bytes, bytes] = dict(scope["headers"])
        settings = get_settings()
        limit: int | None = None
        if path.startswith("/api/datasets"):
            bad = admin_check(headers.get(b"authorization", b"").decode("latin-1") or None)
            if bad:
                await _reply(send, *bad)          # answered without reading a single byte of the body
                return
            limit = settings.dataset_max_bytes + MULTIPART_OVERHEAD
        elif path == "/webhooks/evolution":
            limit = settings.webhook_max_bytes
        if limit is None:
            await self.app(scope, receive, send)
            return
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    await _reply(send, 413, "request body too large")
                    return
            except ValueError:
                await _reply(send, 400, "invalid content-length")
                return
        seen = 0
        replied = False

        async def capped_receive() -> Message:        # chunked bodies have no Content-Length: count them as they arrive
            nonlocal seen, replied
            if replied:
                return {"type": "http.disconnect"}
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    # FastAPI turns any error raised while it reads the body into a 400, so answer 413 here and end the stream.
                    replied = True
                    await _reply(send, 413, "request body too large")
                    return {"type": "http.disconnect"}
            return msg

        async def guarded_send(msg: Message) -> None:
            if not replied:                            # after our 413 anything the app still tries to send is dropped
                await send(msg)

        try:
            await self.app(scope, capped_receive, guarded_send)
        except Exception:
            if not replied:
                raise

