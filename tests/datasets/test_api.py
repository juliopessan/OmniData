"""POST /api/datasets/{kind}: auth, limits, dry-run default, import, listing."""
import pytest
from fastapi.testclient import TestClient

from omnidata.api.app import create_app
from omnidata.config import get_settings
from omnidata.db import connect

from ..conftest import TEST_DSN
from .test_datasets import DATA

AUTH = {"Authorization": "Bearer s3cret-token"}


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "s3cret-token")
    monkeypatch.setenv("CORS_ORIGINS", "https://omnidata-web-eta.vercel.app")
    monkeypatch.setenv("DATASET_MAX_BYTES", "400000")
    get_settings.cache_clear()
    yield TestClient(create_app(lambda: connect(TEST_DSN)))
    get_settings.cache_clear()


def post(c, data=DATA, kind="deals", name="d.csv", headers=AUTH, **form):
    return c.post(f"/api/datasets/{kind}", files={"file": (name, data, "text/csv")}, data=form, headers=headers)


def deal_count(conn):
    with conn.cursor() as cur:
        cur.execute("select count(*) n from silver.deal where hs_deal_id like 'up:%'"); return cur.fetchone()["n"]


def test_auth_is_required_and_constant_time_style(client):
    assert post(client, headers={}).status_code == 401
    assert post(client, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/datasets").status_code == 401


def test_uploads_are_disabled_without_a_token(conn, monkeypatch):
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    get_settings.cache_clear()
    c = TestClient(create_app(lambda: connect(TEST_DSN)))
    assert post(c).status_code == 503
    get_settings.cache_clear()


def test_default_is_dry_run_then_apply(client, conn):
    r = post(client)
    assert r.status_code == 200 and r.json()["status"] == "validated" and r.json()["report"]["ok"] and deal_count(conn) == 0
    r = post(client, dry_run="false")
    assert r.status_code == 200 and r.json()["status"] == "imported" and r.json()["imported"]["deals"] == 63 and deal_count(conn) == 63


def test_rejected_upload_is_422_with_line_level_report(client, conn):
    r = post(client, DATA + "9,X,Qualificação,abc,\r\n".encode(), dry_run="false")
    j = r.json()
    assert r.status_code == 422 and j["status"] == "rejected" and j["report"]["errors"][0]["column"] == "Valor" and deal_count(conn) == 0


def test_oversize_wrong_type_and_binary(client):
    assert post(client, b"x" * 400_001).status_code == 413
    assert post(client, b"a,b\n1,2\n", name="a.exe").json()["code"] == "bad_type"
    assert post(client, b"\x00\x01\x02" * 10, name="a.csv").status_code == 422
    assert post(client, kind="nope").status_code == 404


def test_history_and_public_helpers(client):
    post(client, dry_run="false")
    hist = client.get("/api/datasets", headers=AUTH).json()
    assert hist[0]["status"] == "imported" and hist[0]["imported_rows"] == 63 and "filename" in hist[0]
    t = client.get("/api/datasets/deals/template.csv")
    assert t.status_code == 200 and t.content.startswith(b"\xef\xbb\xbf") and b"ID do registro" in t.content
    assert client.get("/api/datasets/spec").json()["kinds"][0]["key"] == "deals"


def test_cors_only_for_configured_origin(client):
    ok = client.options("/api/datasets/deals", headers={"Origin": "https://omnidata-web-eta.vercel.app", "Access-Control-Request-Method": "POST",
                                                        "Access-Control-Request-Headers": "authorization"})
    bad = client.options("/api/datasets/deals", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "https://omnidata-web-eta.vercel.app"
    assert "access-control-allow-origin" not in bad.headers
