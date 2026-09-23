"""Auth and size limits are enforced BEFORE the body is read (found by a local test: a 300 MB upload with a wrong token was fully
received and spooled to disk before the 401). These tests speak ASGI directly so they can count the bytes the server consumed."""
import asyncio

from omnidata.api.app import create_app
from omnidata.api.guard import MULTIPART_OVERHEAD
from omnidata.config import get_settings


def _call(app, method, path, headers=None, chunks=(b"",), declared=None):
    hdrs = {k.lower(): v for k, v in (headers or {}).items()}
    if declared is not None:
        hdrs["content-length"] = str(declared)
    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "scheme": "http",
             "http_version": "1.1", "server": ("t", 80), "client": ("c", 1), "headers": [(k.encode(), v.encode()) for k, v in hdrs.items()]}
    stream, consumed, sent = list(chunks), {"reads": 0, "bytes": 0}, []

    async def receive():
        consumed["reads"] += 1
        if not stream:
            return {"type": "http.disconnect"}
        body = stream.pop(0)
        consumed["bytes"] += len(body)
        return {"type": "http.request", "body": body, "more_body": bool(stream)}

    async def send(msg):
        sent.append(msg)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["status"], dict(start["headers"]), consumed


def _app(monkeypatch, **env):
    for k, v in {"ADMIN_API_TOKEN": "s3cret-token", **env}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return create_app()


def test_a_bad_or_missing_token_is_refused_without_reading_any_of_the_body(monkeypatch):
    app = _app(monkeypatch)
    for auth in ({}, {"authorization": "Bearer wrong"}, {"authorization": "Basic abc"}):
        status, hdr, used = _call(app, "POST", "/api/datasets/deals", auth, chunks=[b"x" * 1000] * 50, declared=50_000_000)
        assert status == 401 and used["reads"] == 0 and used["bytes"] == 0
        assert hdr[b"www-authenticate"] == b"Bearer"


def test_uploads_are_disabled_with_503_when_no_token_is_configured_and_still_read_nothing(monkeypatch):
    app = _app(monkeypatch, ADMIN_API_TOKEN="")
    status, _, used = _call(app, "POST", "/api/datasets/deals", {"authorization": "Bearer anything"}, chunks=[b"x"] * 5)
    assert status == 503 and used["reads"] == 0


def test_a_declared_size_over_the_limit_is_refused_before_reading(monkeypatch):
    app = _app(monkeypatch, DATASET_MAX_BYTES="1000")
    over = 1000 + MULTIPART_OVERHEAD + 1
    status, _, used = _call(app, "POST", "/api/datasets/deals", {"authorization": "Bearer s3cret-token"}, chunks=[b"x"] * 3, declared=over)
    assert status == 413 and used["reads"] == 0
    status, _, used = _call(app, "POST", "/api/datasets/deals", {"authorization": "Bearer s3cret-token"}, declared="abc")
    assert status == 400 and used["reads"] == 0


def test_a_chunked_upload_without_content_length_is_cut_off_at_the_limit(monkeypatch):
    app = _app(monkeypatch, DATASET_MAX_BYTES="1000")
    chunk = b"x" * 100_000                                   # 20 chunks = 2 MB offered; the limit is about 201 KB
    head = b'--b\r\nContent-Disposition: form-data; name="file"; filename="x.csv"\r\nContent-Type: text/csv\r\n\r\n'
    hdrs = {"authorization": "Bearer s3cret-token", "content-type": "multipart/form-data; boundary=b"}
    status, _, used = _call(app, "POST", "/api/datasets/deals", hdrs, chunks=[head + chunk] + [chunk] * 19)
    assert status == 413
    assert used["bytes"] <= 1000 + MULTIPART_OVERHEAD + len(chunk)      # stopped within one chunk of the limit, not at 2 MB


def test_the_evolution_webhook_body_is_capped_before_the_secret_is_checked(monkeypatch):
    app = _app(monkeypatch, WEBHOOK_MAX_BYTES="5000", EVOLUTION_WEBHOOK_SECRET="app-secret")
    status, _, used = _call(app, "POST", "/webhooks/evolution", {"x-omnidata-secret": "wrong"}, chunks=[b"x"], declared=6000)
    assert status == 413 and used["reads"] == 0
    # Evolution's own auth is a plain header (unlike Meta's HMAC, which needed the body to compute the signature),
    # so the route checks it via FastAPI's Header() dependency BEFORE ever touching the body — a missing header is
    # refused without reading a single byte, even faster than the size cap below.
    status, _, used = _call(app, "POST", "/webhooks/evolution", chunks=[b"x" * 2000] * 5)
    assert status == 401 and used["reads"] == 0
    # With a VALID header the route proceeds to read the body — that read still goes through the size cap.
    status, _, used = _call(app, "POST", "/webhooks/evolution", {"x-omnidata-secret": "app-secret"}, chunks=[b"x" * 2000] * 5)
    assert status == 413 and used["bytes"] <= 5000 + 2000
    status, _, _ = _call(app, "POST", "/webhooks/evolution", {"x-omnidata-secret": "wrong"}, chunks=[b"{}"], declared=2)
    assert status == 401                                       # a small body still reaches the secret check, which refuses it


def test_reads_and_other_routes_are_untouched(monkeypatch):
    app = _app(monkeypatch)
    status, _, _ = _call(app, "GET", "/api/datasets/spec")
    assert status == 200
    status, _, _ = _call(app, "GET", "/healthz")
    assert status == 200


def test_the_guard_answer_carries_cors_headers_so_the_browser_can_show_it(monkeypatch):
    app = _app(monkeypatch, CORS_ORIGINS="https://omnidata-web-eta.vercel.app")
    _, hdr, _ = _call(app, "POST", "/api/datasets/deals", {"origin": "https://omnidata-web-eta.vercel.app"})
    assert hdr[b"access-control-allow-origin"] == b"https://omnidata-web-eta.vercel.app"
    _, hdr, _ = _call(app, "POST", "/api/datasets/deals", {"origin": "https://evil.example"})
    assert b"access-control-allow-origin" not in hdr
