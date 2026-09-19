from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


def add_user(conn: Any, phone: str, owner: str, role: str = "rep", status: str = "active", manager: str | None = None, name: str = "Ana") -> str:
    with conn.cursor() as cur:
        cur.execute("insert into app.app_user (hs_owner_id, phone_e164, display_name, role, status, manager_user_id) "
                    "values (%s,%s,%s,%s,%s,%s) returning id", (owner, phone, name, role, status, manager))
        uid = str(cur.fetchone()["id"])
    conn.commit()
    return uid


def inbound(conn: Any, wa_id: str, phone: str, kind: str = "text", **body: Any) -> None:
    body["from"] = phone
    with conn.cursor() as cur:
        cur.execute("insert into app.wa_message (wa_message_id, direction, kind, payload) values (%s,'in',%s,%s)", (wa_id, kind, Jsonb(body)))
    conn.commit()
