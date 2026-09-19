"""Resilient HubSpot client (FR-ING-3): token-bucket limits, backoff honoring Retry-After,
pagination, and search-cap-safe window slicing. Never logs tokens or payloads."""
from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

BASE_URL = "https://api.hubapi.com"
SEARCH_CAP = 10_000  # the CRM search endpoint caps results per query
PAGE_SIZE = 100


class HubSpotError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HubSpot {status}: {message}")
        self.status = status


class WindowOverflowError(RuntimeError):
    """A window still returns >= SEARCH_CAP results after being reduced to the minimum width."""


class TokenBucket:
    def __init__(self, rate: float, capacity: float | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.rate = rate
        self.capacity = capacity if capacity is not None else max(rate, 1.0)
        self._tokens = self.capacity
        self._clock, self._sleep = clock, sleep
        self._last = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await self._sleep((1 - self._tokens) / self.rate)


def to_ms(dt: datetime) -> int:
    return int(dt.astimezone(UTC).timestamp() * 1000)


class HubSpotClient:
    def __init__(
        self, token: str, *, rps: float = 8, search_rps: float = 4, max_retries: int = 6,
        base_url: str = BASE_URL, transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url, transport=transport, timeout=30.0,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        self._general = TokenBucket(rps, sleep=sleep)
        self._search = TokenBucket(search_rps, sleep=sleep)
        self._max_retries = max_retries
        self._sleep = sleep
        self.calls = 0  # observable in tests

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(self, method: str, path: str, *, json: Any = None,
                      params: dict[str, Any] | None = None, search: bool = False) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            await (self._search if search else self._general).acquire()
            self.calls += 1
            try:
                resp = await self._http.request(method, path, json=json, params=params)
            except httpx.TransportError as exc:
                if attempt == self._max_retries:
                    raise HubSpotError(0, f"transport error: {type(exc).__name__}") from exc
                await self._sleep(self._backoff(attempt))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == self._max_retries:
                    raise HubSpotError(resp.status_code, "retries exhausted")
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() \
                    else self._backoff(attempt)
                await self._sleep(delay)
                continue
            if resp.status_code >= 400:
                raise HubSpotError(resp.status_code, resp.text[:200])
            return resp.json() if resp.content else {}
        raise AssertionError("unreachable")

    @staticmethod
    def _backoff(attempt: int) -> float:
        return float(min(60.0, 2 ** attempt + random.uniform(0, 0.5)))

    # ---- simple GET listings -------------------------------------------------
    async def paged_get(self, path: str, params: dict[str, Any] | None = None) -> AsyncIterator[dict[str, Any]]:
        params = dict(params or {})
        while True:
            data = await self.request("GET", path, params=params)
            for r in data.get("results", []):
                yield r
            after = (data.get("paging") or {}).get("next", {}).get("after")
            if not after:
                return
            params["after"] = after

    async def owners(self) -> list[dict[str, Any]]:
        return [o async for o in self.paged_get("/crm/v3/owners", {"limit": 100})]

    async def pipelines(self, object_type: str = "deals") -> list[dict[str, Any]]:
        res: list[dict[str, Any]] = (await self.request("GET", f"/crm/v3/pipelines/{object_type}")).get("results", [])
        return res

    async def property_schema(self, object_type: str) -> list[dict[str, Any]]:
        res: list[dict[str, Any]] = (await self.request("GET", f"/crm/v3/properties/{object_type}")).get("results", [])
        return res

    async def archived(self, object_type: str, properties: list[str]) -> AsyncIterator[dict[str, Any]]:
        async for r in self.paged_get(f"/crm/v3/objects/{object_type}",
                                      {"archived": "true", "limit": 100, "properties": ",".join(properties)}):
            yield r

    # ---- search with window slicing -----------------------------------------
    def _search_body(self, modified_prop: str, start: datetime, end: datetime, properties: list[str],
                     limit: int, after: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "filterGroups": [{"filters": [
                {"propertyName": modified_prop, "operator": "GTE", "value": str(to_ms(start))},
                {"propertyName": modified_prop, "operator": "LT", "value": str(to_ms(end))},
            ]}],
            "sorts": [{"propertyName": modified_prop, "direction": "ASCENDING"}],
            "properties": properties, "limit": limit,
        }
        if after:
            body["after"] = after
        return body

    async def window_total(self, object_type: str, modified_prop: str, start: datetime, end: datetime) -> int:
        body = self._search_body(modified_prop, start, end, [], 1, None)
        data = await self.request("POST", f"/crm/v3/objects/{object_type}/search", json=body, search=True)
        return int(data.get("total", 0))

    async def search_window(self, object_type: str, modified_prop: str, properties: list[str],
                            start: datetime, end: datetime) -> AsyncIterator[dict[str, Any]]:
        """Yield every object modified in [start, end). Splits the window until each slice is below the cap."""
        total = await self.window_total(object_type, modified_prop, start, end)
        if total >= SEARCH_CAP:
            if end - start <= timedelta(seconds=1):
                raise WindowOverflowError(f"{object_type} {start.isoformat()} still >= {SEARCH_CAP}")
            mid = start + (end - start) / 2
            async for r in self.search_window(object_type, modified_prop, properties, start, mid):
                yield r
            async for r in self.search_window(object_type, modified_prop, properties, mid, end):
                yield r
            return
        after: str | None = None
        while True:
            body = self._search_body(modified_prop, start, end, properties, PAGE_SIZE, after)
            data = await self.request("POST", f"/crm/v3/objects/{object_type}/search", json=body, search=True)
            for r in data.get("results", []):
                yield r
            after = (data.get("paging") or {}).get("next", {}).get("after")
            if not after:
                return

    # ---- batch reads ---------------------------------------------------------
    async def deals_with_history(self, ids: list[str], history: list[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i in range(0, len(ids), 50):  # HubSpot caps history batch reads
            body = {"inputs": [{"id": x} for x in ids[i:i + 50]], "propertiesWithHistory": history}
            out += (await self.request("POST", "/crm/v3/objects/deals/batch/read", json=body)).get("results", [])
        return out

    async def associations(self, from_type: str, to_type: str, ids: list[str]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for i in range(0, len(ids), 100):
            body = {"inputs": [{"id": x} for x in ids[i:i + 100]]}
            data = await self.request("POST", f"/crm/v4/associations/{from_type}/{to_type}/batch/read", json=body)
            for row in data.get("results", []):
                result[str(row["from"]["id"])] = [str(t["toObjectId"]) for t in row.get("to", [])]
        return result
