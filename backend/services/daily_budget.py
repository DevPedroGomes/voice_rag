"""
Daily ceiling on paid provider calls, for a demo that is open to the internet.

Why this exists separately from the per-session and per-IP limits: those bound
what one visitor can do. Neither bounds what *everyone* can do. A modest amount
of traffic, or one person cycling IPs, walks straight past both and the only
thing that notices is the invoice.

Design notes, all of them learned the hard way:

- The budget is consumed **before** the provider is called, never after. Counting
  after the fact means a burst of concurrent requests all pass the check while
  none of them has been counted yet.
- Day boundaries are UTC, so the reset does not move with the server timezone.
- State lives on disk, because a counter in memory silently resets on every
  deploy, which is exactly when traffic is most likely to be replayed.
- The kill switch is an environment variable rather than a code change, so
  stopping the bleeding does not require a build.
- If the state file is unreadable, the answer is to refuse, not to allow. A
  budget that fails open is not a budget.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _state_path() -> Path:
    return Path(os.getenv("DAILY_BUDGET_PATH", "/data/daily_budget.json"))


def _kill_switch_on() -> bool:
    return os.getenv("DEMO_KILL_SWITCH", "") == "1"


def _read_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {"date": _today_utc(), "used": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # Refuse rather than reset: a corrupt file must not hand out a fresh
        # allowance to whoever corrupted it.
        raise RuntimeError(f"daily budget state unreadable: {exc}") from exc

    if state.get("date") != _today_utc():
        return {"date": _today_utc(), "used": {}}
    return state


def _write_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file in the same directory and rename, so a crash midway
    # leaves the previous state intact instead of a truncated file.
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".budget-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow.timestamp() + 86400) - now.timestamp()))


async def consume(kind: str, limit: int, units: int = 1) -> tuple[bool, int]:
    """
    Try to spend `units` from today's allowance for `kind`.

    Returns (allowed, remaining_after). When it returns False nothing was
    consumed, so a refused call costs the caller nothing.
    """
    if _kill_switch_on():
        logger.warning("daily_budget.kill_switch_active kind=%s", kind)
        return False, 0

    async with _lock:
        try:
            state = _read_state()
        except RuntimeError:
            logger.exception("daily_budget.state_unreadable kind=%s", kind)
            return False, 0

        used = int(state["used"].get(kind, 0))
        if used + units > limit:
            logger.warning(
                "daily_budget.exhausted kind=%s used=%d limit=%d", kind, used, limit
            )
            return False, 0

        state["used"][kind] = used + units
        try:
            _write_state(state)
        except OSError:
            # Could not record the spend, so do not authorise it. Otherwise the
            # same call is free forever.
            logger.exception("daily_budget.write_failed kind=%s", kind)
            return False, 0

        remaining = limit - state["used"][kind]
        return True, remaining


async def refund(kind: str, units: int = 1) -> None:
    """
    Give units back when the provider call never happened (it failed before
    reaching them, or was rejected upfront). Best effort: a lost refund costs a
    little headroom, an unrecorded spend costs money.
    """
    async with _lock:
        try:
            state = _read_state()
        except RuntimeError:
            return
        used = int(state["used"].get(kind, 0))
        state["used"][kind] = max(0, used - units)
        try:
            _write_state(state)
        except OSError:
            logger.exception("daily_budget.refund_write_failed kind=%s", kind)


async def snapshot() -> dict:
    """Current usage, for the demo-limits badge and for health checks."""
    async with _lock:
        try:
            state = _read_state()
        except RuntimeError:
            return {"date": _today_utc(), "used": {}, "degraded": True}
        return {**state, "kill_switch": _kill_switch_on()}
