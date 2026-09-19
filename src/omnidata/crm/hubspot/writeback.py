"""HubSpot writes (notes, tasks, deal updates, archive-for-undo). Callers own confirmation/audit (FR-WRT)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .client import HubSpotClient, HubSpotError, to_ms

# HubSpot-defined default association type ids (note->deal 214, task->deal 216).
# TODO(OPEN-1): verify against the portal's API before production; they are stable in HubSpot docs.
NOTE_TO_DEAL, TASK_TO_DEAL = 214, 216


def _assoc(deal_id: str, type_id: int) -> list[dict[str, Any]]:
    return [{"to": {"id": deal_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": type_id}]}]


class HubSpotWriter:
    def __init__(self, client: HubSpotClient) -> None:
        self._c = client

    async def create_note(self, deal_id: str, text: str, owner_id: str | None = None) -> str:
        props: dict[str, Any] = {"hs_note_body": text, "hs_timestamp": to_ms(datetime.now(UTC))}
        if owner_id:
            props["hubspot_owner_id"] = owner_id
        r = await self._c.request("POST", "/crm/v3/objects/notes",
                                  json={"properties": props, "associations": _assoc(deal_id, NOTE_TO_DEAL)})
        return str(r["id"])

    async def create_task(self, deal_id: str, title: str, due: datetime, owner_id: str | None = None) -> str:
        props: dict[str, Any] = {"hs_task_subject": title, "hs_task_status": "NOT_STARTED", "hs_task_type": "TODO",
                                 "hs_timestamp": to_ms(due)}
        if owner_id:
            props["hubspot_owner_id"] = owner_id
        r = await self._c.request("POST", "/crm/v3/objects/tasks",
                                  json={"properties": props, "associations": _assoc(deal_id, TASK_TO_DEAL)})
        return str(r["id"])

    async def get_deal_props(self, deal_id: str, props: list[str]) -> dict[str, Any]:
        r = await self._c.request("GET", f"/crm/v3/objects/deals/{deal_id}", params={"properties": ",".join(props)})
        return dict(r.get("properties", {}))

    async def update_deal(self, deal_id: str, props: dict[str, Any]) -> dict[str, Any]:
        return await self._c.request("PATCH", f"/crm/v3/objects/deals/{deal_id}", json={"properties": props})

    async def update_object(self, object_type: str, object_id: str, props: dict[str, Any]) -> dict[str, Any]:
        return await self._c.request("PATCH", f"/crm/v3/objects/{object_type}/{object_id}", json={"properties": props})

    async def archive(self, object_type: str, object_id: str) -> None:
        try:
            await self._c.request("DELETE", f"/crm/v3/objects/{object_type}/{object_id}")
        except HubSpotError as exc:
            if exc.status != 404:  # already gone = already undone
                raise
