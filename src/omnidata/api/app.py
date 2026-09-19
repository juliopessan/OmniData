"""FastAPI app: WhatsApp webhook + health. Everything else happens in the worker (D4, D6)."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx
import psycopg
from fastapi import FastAPI, Response

from ..bot.webhook import router as webhook_router
from ..config import get_settings
from ..db import connect

log = logging.getLogger("omnidata.api")


def create_app(connect_fn: Callable[[], psycopg.Connection[Any]] | None = None) -> FastAPI:
    app = FastAPI(title="OmniData", docs_url=None, redoc_url=None)
    app.state.connect = connect_fn or connect
    app.include_router(webhook_router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(response: Response) -> dict[str, Any]:
        checks: dict[str, str] = {}
        try:
            with app.state.connect() as conn, conn.cursor() as cur:
                cur.execute("select 1")
            checks["db"] = "ok"
        except Exception:
            checks["db"] = "fail"
        s = get_settings()
        if s.hubspot_access_token:
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    r = await c.get("https://api.hubapi.com/crm/v3/owners", params={"limit": 1},
                                    headers={"Authorization": f"Bearer {s.hubspot_access_token}"})
                checks["hubspot"] = "ok" if r.status_code < 400 else "fail"
            except httpx.HTTPError:
                checks["hubspot"] = "fail"
        else:
            checks["hubspot"] = "not_configured"
        if "fail" in checks.values():
            response.status_code = 503
        return checks

    return app


def app_factory() -> FastAPI:  # uvicorn --factory omnidata.api.app:app_factory
    return create_app()
