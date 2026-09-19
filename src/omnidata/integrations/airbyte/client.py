"""Airbyte public API client (Cloud or self-managed). Auth: client credentials -> bearer token that lives 15 min.
Endpoints per Airbyte docs: POST /applications/token, GET /connections, POST /jobs {connectionId, jobType}, GET /jobs/{id}."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

TERMINAL = {"succeeded", "failed", "cancelled", "incomplete"}


class AirbyteError(RuntimeError):
    pass


@dataclass(frozen=True)
class Job:
    id: int
    status: str
    connection_id: str | None = None
    rows_synced: int | None = None
    bytes_synced: int | None = None

    @property
    def done(self) -> bool:
        return self.status in TERMINAL

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"


def api_base(url: str) -> str:
    """Cloud: https://api.airbyte.com/v1 · self-managed: <url>/api/public/v1"""
    u = url.rstrip("/")
    return f"{u}/v1" if u.endswith("api.airbyte.com") else f"{u}/api/public/v1"


class AirbyteClient:
    def __init__(self, url: str, client_id: str, client_secret: str, transport: httpx.AsyncBaseTransport | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._base = api_base(url)
        self._cid, self._secret = client_id, client_secret
        self._http = httpx.AsyncClient(transport=transport, timeout=30.0)
        self._clock, self._sleep = clock, sleep
        self._token: str | None = None
        self._expires = 0.0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _auth(self, force: bool = False) -> str:
        if self._token and not force and self._clock() < self._expires:
            return self._token
        try:
            r = await self._http.post(f"{self._base}/applications/token", json={
                "client_id": self._cid, "client_secret": self._secret, "grant-type": "client_credentials"})
        except httpx.TransportError as exc:
            raise AirbyteError(f"transport: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise AirbyteError(f"token request failed: HTTP {r.status_code}")
        d = r.json()
        self._token = str(d["access_token"])
        self._expires = self._clock() + max(60.0, float(d.get("expires_in", 900)) - 60.0)  # refresh a minute early
        return self._token

    async def _request(self, method: str, path: str, *, json: Any = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in (0, 1):
            token = await self._auth(force=attempt == 1)
            try:
                r = await self._http.request(method, f"{self._base}{path}", json=json, params=params,
                                             headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
            except httpx.TransportError as exc:
                raise AirbyteError(f"transport: {type(exc).__name__}") from exc
            if r.status_code == 401 and attempt == 0:
                continue  # token expired early: fetch a new one once
            if r.status_code >= 400:
                raise AirbyteError(f"{method} {path}: HTTP {r.status_code}")
            return dict(r.json()) if r.content else {}
        raise AirbyteError("unauthorized")

    @staticmethod
    def _job(d: dict[str, Any]) -> Job:
        return Job(int(d["jobId"]), str(d["status"]).lower(), d.get("connectionId"), d.get("rowsSynced"), d.get("bytesSynced"))

    async def list_connections(self, workspace_ids: list[str] | None = None) -> list[dict[str, Any]]:
        d = await self._request("GET", "/connections", params={"workspaceIds": ",".join(workspace_ids)} if workspace_ids else None)
        return list(d.get("data", []))

    async def trigger_sync(self, connection_id: str) -> Job:
        return self._job(await self._request("POST", "/jobs", json={"connectionId": connection_id, "jobType": "sync"}))

    async def get_job(self, job_id: int) -> Job:
        return self._job(await self._request("GET", f"/jobs/{job_id}"))

    async def wait(self, job_id: int, *, timeout: float = 1800.0, poll: float = 10.0) -> Job:
        deadline = self._clock() + timeout
        while True:
            job = await self.get_job(job_id)
            if job.done:
                return job
            if self._clock() >= deadline:
                raise AirbyteError(f"job {job_id} still {job.status} after {int(timeout)}s")
            await self._sleep(poll)
