"""Identity and permissions (FR-BOT-2). Scope is decided here, in code — never taken from model output."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import psycopg

Role = Literal["rep", "manager", "admin"]
Conn = psycopg.Connection[Any]


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Role
    hs_owner_id: str
    display_name: str | None
    owner_ids: frozenset[str] | None  # None = every owner (admin)

    def can_see_owner(self, owner_id: str | None) -> bool:
        return self.owner_ids is None or (owner_id is not None and owner_id in self.owner_ids)

    def owner_clause(self, column: str = "hs_owner_id") -> tuple[str, list[Any]]:
        """SQL fragment + params restricting `column` to the owners this principal may see."""
        if self.owner_ids is None:
            return "true", []
        return f"{column} = any(%s)", [sorted(self.owner_ids)]


def resolve_by_phone(conn: Conn, phone_e164: str) -> Principal | None:
    """Only ACTIVE users resolve. Unknown, invited, paused and revoked numbers get nothing."""
    with conn.cursor() as cur:
        cur.execute("select id, role, hs_owner_id, display_name from app.app_user "
                    "where phone_e164 = %s and status = 'active'", (phone_e164,))
        u = cur.fetchone()
        if not u:
            return None
        owners: frozenset[str] | None
        if u["role"] == "admin":
            owners = None
        elif u["role"] == "manager":
            cur.execute("select hs_owner_id from app.app_user where manager_user_id = %s and status = 'active'", (u["id"],))
            owners = frozenset({u["hs_owner_id"], *(r["hs_owner_id"] for r in cur.fetchall())})
        else:
            owners = frozenset({u["hs_owner_id"]})
    return Principal(str(u["id"]), u["role"], u["hs_owner_id"], u["display_name"], owners)
