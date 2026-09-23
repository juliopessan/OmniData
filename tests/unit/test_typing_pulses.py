"""The "digitando..." indicator pulses (compose/pause/compose) instead of one static call, like a person actually
typing. asyncio.sleep is monkeypatched so the test doesn't really wait ~7s for the full pattern."""
from omnidata.bot import orchestrator

from ..fakes import FakeGateway


async def test_full_pattern_when_the_budget_covers_it(monkeypatch):
    monkeypatch.setattr(orchestrator.asyncio, "sleep", lambda *_: _noop())
    gw = FakeGateway()
    await orchestrator._typing_pulses(gw, "+5511900000001", budget=10.0)
    assert gw.presence == [("+5511900000001", True), ("+5511900000001", False), ("+5511900000001", True)]


async def test_truncated_pattern_when_the_budget_is_smaller(monkeypatch):
    monkeypatch.setattr(orchestrator.asyncio, "sleep", lambda *_: _noop())
    gw = FakeGateway()
    await orchestrator._typing_pulses(gw, "+5511900000001", budget=3.0)  # 2s composing + 1s of the 3s pause
    assert gw.presence == [("+5511900000001", True), ("+5511900000001", False)]


async def _noop() -> None:
    return None
