"""GET /api/cockpit/*: auth, conversation list ordering, message thread shape (sales cockpit / shared inbox)."""
import pytest
from fastapi.testclient import TestClient

from omnidata.api.app import create_app
from omnidata.config import get_settings
from omnidata.db import connect

from ..conftest import TEST_DSN
from ..helpers import add_user

AUTH = {"Authorization": "Bearer s3cret-token"}


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "s3cret-token")
    monkeypatch.setenv("CORS_ORIGINS", "https://omnidata-web-eta.vercel.app")
    get_settings.cache_clear()
    yield TestClient(create_app(lambda: connect(TEST_DSN)))
    get_settings.cache_clear()


def out(conn, user_id, text, kind="text"):
    from psycopg.types.json import Jsonb
    with conn.cursor() as cur:
        cur.execute("insert into app.wa_message (user_id, direction, kind, payload, status) values (%s,'out',%s,%s,'done')",
                    (user_id, kind, Jsonb({"text": text})))
    conn.commit()


def inb(conn, user_id, wa_id, phone, text):
    """Mirrors bot/webhook.py::persist_inbound, which looks up and stores user_id at insert time (unlike the
    lighter tests/helpers.py::inbound, used by orchestrator tests that resolve the user by phone instead)."""
    from psycopg.types.json import Jsonb
    with conn.cursor() as cur:
        cur.execute("insert into app.wa_message (wa_message_id, user_id, direction, kind, payload) values (%s,%s,'in','text',%s)",
                    (wa_id, user_id, Jsonb({"from": phone, "text": text})))
    conn.commit()


def test_auth_is_required(client):
    assert client.get("/api/cockpit/conversations").status_code == 401
    assert client.get("/api/cockpit/conversations", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_disabled_without_a_token(conn, monkeypatch):
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    get_settings.cache_clear()
    c = TestClient(create_app(lambda: connect(TEST_DSN)))
    assert c.get("/api/cockpit/conversations").status_code == 503
    get_settings.cache_clear()


def test_conversations_ordered_by_most_recent_message(client, conn):
    a = add_user(conn, "+5511900000001", "9000", status="active", name="Ana")
    r = add_user(conn, "+5511900000002", "9001", status="invited", name="Rafael")
    inb(conn, a, "W1", "+5511900000001", "como estou na meta?")
    out(conn, a, "Você está em 35%.")
    inb(conn, r, "W2", "+5511900000002", "oi")

    rows = client.get("/api/cockpit/conversations", headers=AUTH).json()
    assert [row["id"] for row in rows] == [r, a]  # Rafael's "oi" is the most recent message
    assert rows[0]["last_direction"] == "in" and rows[0]["last_preview"] == "oi"
    assert rows[1]["status"] == "active"


def test_conversations_excludes_revoked_users(client, conn):
    add_user(conn, "+5511900000003", "9002", status="revoked", name="Saiu")
    rows = client.get("/api/cockpit/conversations", headers=AUTH).json()
    assert rows == []


def test_message_thread_is_chronological_and_includes_both_directions(client, conn):
    a = add_user(conn, "+5511900000004", "9003", status="active", name="Ana")
    inb(conn, a, "W3", "+5511900000004", "como estou na meta?")
    out(conn, a, "Você está em 35% da meta.")

    msgs = client.get(f"/api/cockpit/conversations/{a}/messages", headers=AUTH).json()
    assert [m["direction"] for m in msgs] == ["in", "out"]
    assert msgs[0]["text"] == "como estou na meta?" and msgs[1]["text"] == "Você está em 35% da meta."


def test_message_thread_for_unknown_user_is_404(client):
    assert client.get("/api/cockpit/conversations/00000000-0000-0000-0000-000000000000/messages", headers=AUTH).status_code == 404
    assert client.get("/api/cockpit/conversations/not-a-uuid/messages", headers=AUTH).status_code == 404
