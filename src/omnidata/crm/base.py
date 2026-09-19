"""CrmAdapter: HubSpot is the only implementation in v1 (FR-ING-8, P2)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Protocol


class CrmAdapter(Protocol):
    async def search_modified(
        self, object_type: str, properties: list[str], start: datetime, end: datetime
    ) -> AsyncIterator[dict[str, Any]]: ...
