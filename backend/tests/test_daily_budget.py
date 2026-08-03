"""Tests for the daily ceiling on paid provider calls."""

import asyncio
import json
import os

import pytest

from services import daily_budget


@pytest.fixture(autouse=True)
def budget_file(tmp_path, monkeypatch):
    """Point the module at a throwaway file and clear the kill switch."""
    path = tmp_path / "daily_budget.json"
    monkeypatch.setenv("DAILY_BUDGET_PATH", str(path))
    monkeypatch.delenv("DEMO_KILL_SWITCH", raising=False)
    return path


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_consumes_until_the_limit_then_refuses():
    async def scenario():
        results = [await daily_budget.consume("query", limit=3) for _ in range(4)]
        return results

    results = run(scenario())
    assert [allowed for allowed, _ in results] == [True, True, True, False]
    # The refused call must not have been charged, otherwise a denial still costs
    # the next visitor their allowance.
    assert results[2][1] == 0
    assert results[3][1] == 0


def test_state_survives_a_process_restart(budget_file):
    run(daily_budget.consume("query", limit=5))
    assert json.loads(budget_file.read_text())["used"]["query"] == 1

    # Simulate a redeploy: nothing in memory, everything on disk.
    allowed, remaining = run(daily_budget.consume("query", limit=5))
    assert allowed is True
    assert remaining == 3, "an in-memory counter would have reset here"


def test_kinds_do_not_share_an_allowance():
    async def scenario():
        await daily_budget.consume("query", limit=1)
        return await daily_budget.consume("transcribe", limit=1)

    allowed, _ = run(scenario())
    assert allowed is True


def test_refund_returns_the_units():
    async def scenario():
        await daily_budget.consume("query", limit=1)
        await daily_budget.refund("query")
        return await daily_budget.consume("query", limit=1)

    allowed, _ = run(scenario())
    assert allowed is True, "a call that never reached the provider must not be charged"


def test_refund_never_goes_negative():
    async def scenario():
        await daily_budget.refund("query")
        await daily_budget.refund("query")
        return await daily_budget.snapshot()

    snap = run(scenario())
    assert snap["used"].get("query", 0) == 0


def test_kill_switch_refuses_everything(monkeypatch):
    monkeypatch.setenv("DEMO_KILL_SWITCH", "1")
    allowed, _ = run(daily_budget.consume("query", limit=1000))
    assert allowed is False, "the switch has to stop spend without a redeploy"


def test_a_new_utc_day_resets_the_counter(budget_file):
    run(daily_budget.consume("query", limit=1))
    # Rewrite the state as if it were written yesterday.
    state = json.loads(budget_file.read_text())
    state["date"] = "2000-01-01"
    budget_file.write_text(json.dumps(state))

    allowed, _ = run(daily_budget.consume("query", limit=1))
    assert allowed is True


def test_corrupt_state_refuses_instead_of_resetting(budget_file):
    budget_file.write_text("{ this is not json")
    allowed, _ = run(daily_budget.consume("query", limit=1000))
    assert allowed is False, "a budget that fails open is not a budget"


def test_unwritable_state_refuses(budget_file, monkeypatch):
    # If the spend cannot be recorded, authorising it would make that call free
    # forever.
    monkeypatch.setattr(
        daily_budget, "_write_state", lambda _state: (_ for _ in ()).throw(OSError("read-only"))
    )
    allowed, _ = run(daily_budget.consume("query", limit=1000))
    assert allowed is False


def test_concurrent_callers_cannot_oversubscribe():
    """The failure this guards against: ten requests arrive together, all read
    used=0, all pass a limit of 3, and the invoice shows ten calls."""

    async def scenario():
        results = await asyncio.gather(
            *[daily_budget.consume("query", limit=3) for _ in range(10)]
        )
        return sum(1 for allowed, _ in results if allowed)

    loop = asyncio.get_event_loop_policy().new_event_loop()
    granted = loop.run_until_complete(scenario())
    assert granted == 3
