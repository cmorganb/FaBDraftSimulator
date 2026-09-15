"""Tests for the Clock abstraction (WP-07)."""

from __future__ import annotations

import asyncio
import time

import pytest
from fabdraft_core.draft.clock import RealClock, SimClock


@pytest.mark.asyncio
async def test_sim_clock_starts_at_zero_and_advances() -> None:
    clock = SimClock()
    assert clock.now_ms() == 0
    await clock.advance_ms(1500)
    assert clock.now_ms() == 1500


@pytest.mark.asyncio
async def test_sim_clock_resolve_pick_never_waits_in_real_time() -> None:
    clock = SimClock()

    async def slow_but_never_actually_awaited_long() -> str | None:
        return "picked-uid"

    start = time.perf_counter()
    result = await clock.resolve_pick(slow_but_never_actually_awaited_long(), timer_seconds=50.0)
    elapsed = time.perf_counter() - start
    assert result == "picked-uid"
    assert elapsed < 0.1  # nowhere near the nominal 50s timer


@pytest.mark.asyncio
async def test_sim_clock_resolve_pick_passes_through_none() -> None:
    clock = SimClock()

    async def declines() -> str | None:
        return None

    assert await clock.resolve_pick(declines(), timer_seconds=10.0) is None


@pytest.mark.asyncio
async def test_real_clock_advance_ms_actually_sleeps() -> None:
    clock = RealClock()
    start = time.perf_counter()
    await clock.advance_ms(20)
    assert time.perf_counter() - start >= 0.015


@pytest.mark.asyncio
async def test_real_clock_now_ms_increases_with_wall_time() -> None:
    clock = RealClock()
    t0 = clock.now_ms()
    await asyncio.sleep(0.01)
    t1 = clock.now_ms()
    assert t1 > t0


@pytest.mark.asyncio
async def test_real_clock_resolve_pick_returns_result_when_fast_enough() -> None:
    clock = RealClock()

    async def fast() -> str | None:
        return "picked-uid"

    assert await clock.resolve_pick(fast(), timer_seconds=5.0) == "picked-uid"


@pytest.mark.asyncio
async def test_real_clock_resolve_pick_times_out() -> None:
    clock = RealClock()

    async def never_finishes() -> str | None:
        await asyncio.sleep(10)
        return "too-late"

    result = await clock.resolve_pick(never_finishes(), timer_seconds=0.01)
    assert result is None


@pytest.mark.asyncio
async def test_real_clock_resolve_pick_with_no_timer_waits_indefinitely_for_fast_coro() -> None:
    clock = RealClock()

    async def fast() -> str | None:
        return "picked-uid"

    assert await clock.resolve_pick(fast(), timer_seconds=None) == "picked-uid"
