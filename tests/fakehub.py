"""In-memory fake of the HubSpot endpoints OmniData uses (httpx.MockTransport). Scrubbed, synthetic data."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def make_deals(n: int) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        stage = ["s1", "won", "lost"][i % 3]
        created = ms(T0) + i * 3_600_000
        out.append({"id": str(1000 + i), "archived": False, "properties": {
            "dealname": f"Deal {i}", "amount": str(1000 * (i + 1)), "pipeline": "default", "dealstage": stage,
            "hubspot_owner_id": "9001", "createdate": str(created), "closedate": str(created + 86_400_000 * 5),
            "hs_lastmodifieddate": str(created + 60_000), "closed_lost_reason": "price" if stage == "lost" and i % 2 else "",
            "num_associated_contacts": "1"}})
    return out


class FakeHubSpot:
    def __init__(self, deals: int = 9, fail_after_search_calls: int | None = None, cap: int | None = None) -> None:
        self.deals = make_deals(deals)
        self.log: list[str] = []
        self.fail_after = fail_after_search_calls
        self.search_calls = 0
        self.cap = cap  # pretend the search returns this "total" for wide windows (cap testing)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _search(self, obj: str, body: dict[str, Any]) -> httpx.Response:
        self.search_calls += 1
        if self.fail_after is not None and self.search_calls > self.fail_after:
            return httpx.Response(500, json={"message": "boom"})
        flt = {f["operator"]: int(f["value"]) for f in body["filterGroups"][0]["filters"]}
        rows = self.deals if obj == "deals" else []
        rows = [r for r in rows if flt["GTE"] <= int(r["properties"]["hs_lastmodifieddate"]) < flt["LT"]]
        total = len(rows)
        if self.cap is not None and (flt["LT"] - flt["GTE"]) > self.cap:
            total = 10_000  # simulate overflow on wide windows
        after = int(body.get("after") or 0)
        page = rows[after: after + body["limit"]]
        data: dict[str, Any] = {"total": total, "results": page}
        if after + body["limit"] < len(rows):
            data["paging"] = {"next": {"after": str(after + body["limit"])}}
        return httpx.Response(200, json=data)

    def handle(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        self.log.append(f"{req.method} {path}")
        body = json.loads(req.content) if req.content else {}
        if path == "/crm/v3/owners":
            return httpx.Response(200, json={"results": [{"id": "9001", "email": "rep@example.invalid",
                                                          "firstName": "Ana", "lastName": "Souza"}]})
        if path == "/crm/v3/pipelines/deals":
            return httpx.Response(200, json=json.load(open("tests/contract/fixtures/pipelines.json")))
        if path.endswith("/search"):
            return self._search(path.split("/")[4], body)
        if path == "/crm/v3/objects/deals/batch/read":
            res = []
            for inp in body["inputs"]:
                d = next(x for x in self.deals if x["id"] == inp["id"])
                stage = d["properties"]["dealstage"]
                created = int(d["properties"]["createdate"])
                res.append({"id": d["id"], "propertiesWithHistory": {
                    "dealstage": [{"value": stage, "timestamp": str(created + 1000)}, {"value": "s1", "timestamp": str(created)}],
                    "closedate": [{"value": str(created + 9), "timestamp": str(created + 5)}, {"value": str(created + 3), "timestamp": str(created)}],
                    "amount": [], "hubspot_owner_id": []}})
            return httpx.Response(200, json={"results": res})
        if path.startswith("/crm/v4/associations/"):
            return httpx.Response(200, json={"results": [{"from": {"id": i["id"]}, "to": [{"toObjectId": "c1"}]}
                                                         for i in body["inputs"]]})
        if path == "/crm/v3/objects/deals":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(404, json={"message": f"unhandled {path}"})
