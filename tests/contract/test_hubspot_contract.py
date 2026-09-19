"""Recorded, scrubbed HubSpot responses (pagination, mapping of pipelines). No live API unless RUN_LIVE=1."""
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from omnidata.crm.hubspot import mapping as m
from omnidata.crm.hubspot.client import HubSpotClient

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text())


async def test_search_paginates_with_after_cursor():
    pages = [load("search_page1.json"), load("search_page2.json")]
    bodies = []

    def h(req):
        b = json.loads(req.content)
        bodies.append(b)
        return httpx.Response(200, json=pages[1] if b.get("after") else pages[0]) if b["limit"] != 1 \
            else httpx.Response(200, json={"total": 3, "results": []})
    async def nosleep(_): ...
    c = HubSpotClient("t", transport=httpx.MockTransport(h), sleep=nosleep)
    got = [r["id"] async for r in c.search_window("deals", "hs_lastmodifieddate", ["dealname"],
                                                  datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC))]
    assert got == ["101", "102", "103"]
    assert bodies[-1]["after"] == "2" and bodies[-1]["sorts"][0]["direction"] == "ASCENDING"


def test_pipeline_metadata_maps_to_closed_won_lost_flags():
    pipe, stages = m.map_pipeline(load("pipelines.json")["results"][0])
    by = {s["hs_stage_id"]: s for s in stages}
    assert pipe["hs_pipeline_id"] == "default"
    assert by["won"]["is_closed"] and by["won"]["probability"] == 1
    assert by["lost"]["is_closed"] and by["lost"]["probability"] == 0
    assert not by["s1"]["is_closed"]
