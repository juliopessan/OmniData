import json

import httpx
import pytest

from omnidata.crm.hubspot.client import HubSpotClient, HubSpotError, TokenBucket


async def no_sleep(_): ...


def client(handler, sleeps=None, **kw):
    async def sleep(s):
        if sleeps is not None:
            sleeps.append(s)
    return HubSpotClient("tok", transport=httpx.MockTransport(handler), sleep=sleep, **kw)


async def test_429_honors_retry_after_then_succeeds():  # FR-ING-3
    calls, sleeps = [], []

    def h(req):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "7"}) if len(calls) == 1 else httpx.Response(200, json={"ok": 1})
    c = client(h, sleeps)
    assert await c.request("GET", "/x") == {"ok": 1}
    assert 7.0 in sleeps


async def test_5xx_retries_with_backoff_and_gives_up():
    sleeps = []
    c = client(lambda r: httpx.Response(503), sleeps, max_retries=2)
    with pytest.raises(HubSpotError) as e:
        await c.request("GET", "/x")
    assert e.value.status == 503 and len(sleeps) == 2 and sleeps[1] > sleeps[0]


async def test_4xx_fails_fast_without_retry():
    n = []
    c = client(lambda r: (n.append(1), httpx.Response(401, text="nope"))[1])
    with pytest.raises(HubSpotError):
        await c.request("GET", "/x")
    assert len(n) == 1


async def test_token_never_in_error_message():
    c = client(lambda r: httpx.Response(401, text="unauthorized"))
    with pytest.raises(HubSpotError) as e:
        await c.request("GET", "/x")
    assert "tok" not in str(e.value)


async def test_token_bucket_throttles():
    t = [0.0]
    slept = []

    async def sleep(s):
        slept.append(s)
        t[0] += s
    b = TokenBucket(rate=2, capacity=2, clock=lambda: t[0], sleep=sleep)
    for _ in range(4):
        await b.acquire()
    assert sum(slept) == pytest.approx(1.0)  # 2 free tokens, then 2 more at 2 rps


async def test_search_cap_splits_window_until_below_cap():  # FR-ING-3: assert no window returns the cap
    from datetime import UTC, datetime
    seen = []

    def h(req):
        body = json.loads(req.content)
        f = {x["operator"]: int(x["value"]) for x in body["filterGroups"][0]["filters"]}
        width = f["LT"] - f["GTE"]
        if body["limit"] == 1:
            seen.append(width)
            return httpx.Response(200, json={"total": 10_000 if width > 30 * 86_400_000 else 5, "results": []})
        return httpx.Response(200, json={"total": 5, "results": [{"id": str(f["GTE"])}]})
    c = client(h)
    out = [r async for r in c.search_window("deals", "hs_lastmodifieddate", [], datetime(2026, 1, 1, tzinfo=UTC),
                                             datetime(2026, 5, 1, tzinfo=UTC))]
    assert len(out) >= 4 and max(seen) > 30 * 86_400_000  # wide window was probed, then split
