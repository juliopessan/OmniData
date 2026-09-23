"""Read-only API for the sales cockpit (shared inbox): lets management see the real WhatsApp conversations.
Protected by ADMIN_API_TOKEN (bearer), same as the dataset upload API — no new auth mechanism."""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from .guard import require_admin

router = APIRouter(prefix="/api/cockpit", tags=["cockpit"])
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def _preview(payload: dict[str, Any]) -> str | None:
    t = payload.get("text")
    return (t[:140] + "…") if isinstance(t, str) and len(t) > 140 else t


@router.get("/conversations")
async def conversations(request: Request, _: str = Depends(require_admin)) -> list[dict[str, Any]]:
    with request.app.state.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select u.id, u.display_name, u.phone_e164, u.hs_owner_id, u.status, "
            "m.direction as last_direction, m.kind as last_kind, m.payload as last_payload, m.received_at as last_received_at "
            "from app.app_user u left join lateral ("
            "  select direction, kind, payload, received_at from app.wa_message where user_id = u.id order by received_at desc limit 1"
            ") m on true "
            "where u.status in ('invited', 'active') order by m.received_at desc nulls last")
        return [{"id": str(r["id"]), "display_name": r["display_name"], "phone_e164": r["phone_e164"], "hs_owner_id": r["hs_owner_id"],
                 "status": r["status"], "last_direction": r["last_direction"], "last_kind": r["last_kind"],
                 "last_preview": _preview(r["last_payload"]) if r["last_payload"] else None,
                 "last_received_at": r["last_received_at"].isoformat() if r["last_received_at"] else None} for r in cur.fetchall()]


@router.get("/conversations/{user_id}/messages")
async def messages(request: Request, user_id: str, limit: int = 100, _: str = Depends(require_admin)) -> list[dict[str, Any]]:
    if not _UUID.match(user_id):
        raise HTTPException(404, "unknown user")
    limit = max(1, min(limit, 500))
    with request.app.state.connect() as conn, conn.cursor() as cur:
        cur.execute("select id from app.app_user where id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(404, "unknown user")
        cur.execute(
            "select direction, kind, payload, status, error, received_at from app.wa_message "
            "where user_id = %s order by received_at desc limit %s", (user_id, limit))
        rows = cur.fetchall()[::-1]  # oldest -> newest, for a chat thread
        return [{"direction": r["direction"], "kind": r["kind"], "text": r["payload"].get("text"), "status": r["status"],
                 "error": r["error"], "received_at": r["received_at"].isoformat()} for r in rows]
