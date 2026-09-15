"""Clock abstraction (plan section 6.2 concurrency note): "Simulated time
must be decoupled from wall time so that headless batch runs execute
instantly."

`SimClock` never actually waits in real wall-clock time - a pick source is
trusted to resolve promptly (it either returns a `picked_uid` or `None` for
"can't decide," which the engine treats as a timeout with zero real-time
cost). `RealClock` uses `asyncio.wait_for` against the real event loop
clock, for an eventual interactive session (human/LLM-API seats).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from typing import Protocol


class Clock(Protocol):
    def now_ms(self) -> int: ...

    async def advance_ms(self, ms: int) -> None:
        """Account for `ms` of simulated/real elapsed time (e.g. a review
        window), without necessarily blocking for that long.
        """
        ...

    async def resolve_pick(
        self, coro: Awaitable[str | None], timer_seconds: float | None
    ) -> str | None:
        """Await `coro` (a pick source's decision), respecting
        `timer_seconds` (None = no timer, per TRP A.3's last-card case).
        Returns the picked uid, or None on timeout/decline.
        """
        ...


class SimClock:
    """No real waiting: `resolve_pick` just awaits the coroutine directly
    (any timeout behavior is the pick source's own choice, expressed by
    returning None), and `advance_ms` only moves the virtual clock forward.
    This is what makes a full draft run in well under a second.
    """

    def __init__(self) -> None:
        self._now_ms = 0

    def now_ms(self) -> int:
        return self._now_ms

    async def advance_ms(self, ms: int) -> None:
        self._now_ms += ms
        await asyncio.sleep(0)  # yield control, keep this cooperative

    async def resolve_pick(
        self, coro: Awaitable[str | None], timer_seconds: float | None
    ) -> str | None:
        result = await coro
        return result


class RealClock:
    """Uses the real event loop clock. `resolve_pick` enforces
    `timer_seconds` via `asyncio.wait_for`; a real `asyncio.TimeoutError`
    becomes a `None` (timeout) result, matching `SimClock`'s contract.
    """

    def now_ms(self) -> int:
        return int(time.monotonic() * 1000)

    async def advance_ms(self, ms: int) -> None:
        await asyncio.sleep(ms / 1000)

    async def resolve_pick(
        self, coro: Awaitable[str | None], timer_seconds: float | None
    ) -> str | None:
        if timer_seconds is None:
            return await coro
        try:
            return await asyncio.wait_for(coro, timeout=timer_seconds)
        except TimeoutError:
            return None
