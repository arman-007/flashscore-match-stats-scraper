from __future__ import annotations

from types import SimpleNamespace

import pytest

from src import billing as billing_module
from src.billing import Billing


class _Log:
    def info(self, *_a, **_k): ...
    def warning(self, *_a, **_k): ...


class FakeActor:
    log = _Log()

    def __init__(self):
        self.accept = None
        self.pushed = []

    async def push_data(self, rows, charged_event_name=None):
        rows = rows if isinstance(rows, list) else [rows]
        n = len(rows) if self.accept is None else min(self.accept, len(rows))
        self.pushed.append((charged_event_name, rows[:n]))
        return SimpleNamespace(charged_count=n, event_charge_limit_reached=n < len(rows))


@pytest.fixture
def actor(monkeypatch):
    fake = FakeActor()
    monkeypatch.setattr(billing_module, "Actor", fake)
    return fake


async def test_one_event_per_row(actor):
    b = Billing(pay_per_event=True)
    assert await b.push([{"a": 1}, {"a": 2}], billing_module.PLAYER_EVENT) == 2
    assert actor.pushed[0][0] == "player-match"
    assert b.charged["player-match"] == 2 and not b.budget_exhausted


async def test_budget_stops_the_run(actor):
    actor.accept = 1
    b = Billing(pay_per_event=True)
    assert await b.push([{"a": 1}, {"a": 2}], billing_module.MATCH_EVENT) == 1
    assert b.budget_exhausted


async def test_not_monetized_pushes_without_charging(actor):
    b = Billing(pay_per_event=False)
    assert await b.push([{"a": 1}], billing_module.MATCH_EVENT) == 1
    assert actor.pushed[0][0] is None


async def test_unbilled_rows(actor):
    await Billing.push_unbilled({"recordType": "error"})
    assert actor.pushed == [(None, [{"recordType": "error"}])]


def test_the_platform_events_are_never_used():
    events = {billing_module.MATCH_EVENT, billing_module.PLAYER_EVENT}
    assert events == {"match", "player-match"}
