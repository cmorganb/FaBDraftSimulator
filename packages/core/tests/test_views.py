"""Tests for AgentView construction / information policy enforcement
(WP-08, plan section 3.2).

Uses one real draft run (FIXTURE data) as the source of realistic
`DraftState`/event-log snapshots, then fuzzes seat/policy/point-in-draft
combinations against it with Hypothesis - this is more faithful than
hand-rolling arbitrary `DraftState` values, since `DraftState` has
internal consistency constraints (pack_id lineage, pool/pack
complementarity) that are easy to violate with a naive generator but are
guaranteed to hold for anything the real engine actually produces.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fabdraft_core.contracts import Card, DraftEvent, PackConfig, SetSnapshot
from fabdraft_core.draft.engine import run_draft
from fabdraft_core.draft.state import DraftState, fold_draft_events
from fabdraft_core.draft.views import (
    FormatSummary,
    HeroSummary,
    ViewPolicy,
    build_agent_view,
)
from hypothesis import given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_SET_PATH = REPO_ROOT / "data" / "fixtures" / "fixture_set.json"
FIXTURE_PACK_CONFIG_PATH = REPO_ROOT / "data" / "config" / "fixture.pack_config.json"


class FirstAvailablePickSource:
    async def get_pick(self, seat: int, pack: list[Card], deadline_ms: int | None) -> str | None:
        return pack[0].uid


def _load_draft() -> tuple[list[DraftEvent], dict[str, Card], FormatSummary]:
    cards = SetSnapshot.model_validate(json.loads(FIXTURE_SET_PATH.read_text())).cards
    pack_config = PackConfig.model_validate(json.loads(FIXTURE_PACK_CONFIG_PATH.read_text()))

    async def _run() -> list[DraftEvent]:
        _, store = await run_draft(
            session_id="wp08-test",
            seed="wp08-seed",
            cards=cards,
            pack_config=pack_config,
            pick_source=FirstAvailablePickSource(),
        )
        return store.events

    events = asyncio.run(_run())
    catalog = {c.uid: c for c in cards}
    heroes = tuple(
        HeroSummary(h.uid, h.name, tuple(h.classes), tuple(h.talents))
        for h in cards
        if h.object_type == "hero"
    )
    fmt = FormatSummary(deck_size=30, heroes=heroes, basics_available=True)
    return events, catalog, fmt


_EVENTS, _CATALOG, _FORMAT = _load_draft()

PICK_POINTS = [(1, 1), (1, 5), (1, 9), (2, 1), (2, 9), (3, 14)]


def _state_before_pick(round_number: int, pick_number: int) -> tuple[list[DraftEvent], DraftState]:
    idx = next(
        i
        for i, e in enumerate(_EVENTS)
        if e.type in ("PICK_MADE", "PICK_AUTO")
        and e.round == round_number
        and e.pick_number == pick_number
    )
    truncated = _EVENTS[:idx]
    return truncated, fold_draft_events(truncated)


@pytest.mark.parametrize(("round_number", "pick_number"), PICK_POINTS)
def test_every_seats_view_reports_its_own_seat(round_number: int, pick_number: int) -> None:
    events, state = _state_before_pick(round_number, pick_number)
    for seat in range(8):
        view = build_agent_view(
            events, state, seat, _CATALOG, _FORMAT, policy=ViewPolicy(memory_policy="full_recall")
        )
        assert view.seat == seat
        assert view.round == round_number
        assert view.pick_number == pick_number


@given(
    seat=st.integers(min_value=0, max_value=7),
    point=st.sampled_from(PICK_POINTS),
    casual_mode=st.booleans(),
    memory_policy=st.sampled_from(["none", "own_pool", "full_recall"]),
)
@settings(max_examples=150)
def test_property_own_pool_empty_unless_casual_mode(
    seat: int, point: tuple[int, int], casual_mode: bool, memory_policy: str
) -> None:
    """plan WP-08 acceptance: 'own_pool empty unless in a review window or
    casual_mode.' This function only ever builds views mid pick-window (see
    its docstring), so the review-window case is exercised by
    `casual_mode` alone here - own_pool must never appear during active
    picking unless casual_mode relaxes it.
    """
    round_number, pick_number = point
    events, state = _state_before_pick(round_number, pick_number)
    view = build_agent_view(
        events,
        state,
        seat,
        _CATALOG,
        _FORMAT,
        policy=ViewPolicy(memory_policy=memory_policy, casual_mode=casual_mode),  # type: ignore[arg-type]
    )
    if casual_mode:
        assert view.own_pool_visible is True
    else:
        assert view.own_pool_visible is False
        assert view.own_pool == []


@given(seat=st.integers(min_value=0, max_value=7), point=st.sampled_from(PICK_POINTS))
@settings(max_examples=150)
def test_property_view_contains_only_this_seats_own_pack_and_pool(
    seat: int, point: tuple[int, int]
) -> None:
    """plan section 6.2 invariant: 'No event [or view] ever contains
    another seat's pool.' Checks the view's pack/pool exactly matches this
    seat's own DraftState slice - not merely 'is non-empty', but exactly
    the expected uid set, with nothing extra sneaking in from elsewhere.
    """
    round_number, pick_number = point
    events, state = _state_before_pick(round_number, pick_number)
    view = build_agent_view(
        events,
        state,
        seat,
        _CATALOG,
        _FORMAT,
        policy=ViewPolicy(memory_policy="full_recall", casual_mode=True),
    )

    expected_pack_uids = {c.uid for c in state.seat_packs[seat].cards}
    actual_pack_uids = {c.uid for c in view.pack}
    assert actual_pack_uids == expected_pack_uids

    expected_pool_uids = {c.uid for c in state.seat_pools.get(seat, ())}
    actual_pool_uids = {c.uid for c in view.own_pool}
    assert actual_pool_uids == expected_pool_uids

    expected_own_picks_uids = [
        e.payload["picked_uid"]
        for e in events
        if e.type in ("PICK_MADE", "PICK_AUTO") and e.seat == seat and e.round == round_number
    ]
    actual_own_picks_uids = [c.uid for c in view.memory.own_picks_this_round]
    assert actual_own_picks_uids == expected_own_picks_uids


def test_full_recall_seen_packs_are_all_draftable_sized() -> None:
    events, state = _state_before_pick(1, 5)
    view = build_agent_view(
        events, state, 3, _CATALOG, _FORMAT, policy=ViewPolicy(memory_policy="full_recall")
    )
    # every entry should be a shrinking draftable pack (14, 13, 12, 11, 10
    # by pick 5) - never 16 (the PACK_OPENED payload's un-trimmed size,
    # which would mean extras leaked into memory).
    assert [len(p) for p in view.memory.seen_packs] == [14, 13, 12, 11, 10]


def test_none_memory_policy_hides_own_picks_and_seen_packs() -> None:
    events, state = _state_before_pick(1, 5)
    view = build_agent_view(
        events, state, 3, _CATALOG, _FORMAT, policy=ViewPolicy(memory_policy="none")
    )
    assert view.memory.own_picks_this_round == []
    assert view.memory.seen_packs == []


def test_own_pool_memory_policy_reveals_own_picks_but_not_seen_packs() -> None:
    events, state = _state_before_pick(1, 5)
    view = build_agent_view(
        events, state, 3, _CATALOG, _FORMAT, policy=ViewPolicy(memory_policy="own_pool")
    )
    assert len(view.memory.own_picks_this_round) == 4
    assert view.memory.seen_packs == []


def test_raises_if_seat_out_of_range() -> None:
    events, state = _state_before_pick(1, 1)
    with pytest.raises(ValueError, match="not in this pod"):
        build_agent_view(events, state, 99, _CATALOG, _FORMAT)


def test_raises_if_not_mid_pick_window() -> None:
    with pytest.raises(ValueError, match="phase='drafting'"):
        build_agent_view([], DraftState(), 0, _CATALOG, _FORMAT)


def test_raises_if_round_is_not_positive() -> None:
    from dataclasses import replace

    events, state = _state_before_pick(1, 1)
    bad_state = replace(state, round=0)
    with pytest.raises(ValueError, match="state.round must be >= 1"):
        build_agent_view(events, bad_state, 0, _CATALOG, _FORMAT)


def test_raises_if_seat_has_no_current_pack() -> None:
    # round complete resets seat_packs to {} - phase stays "drafting" only
    # briefly; force the scenario directly via a hand-built state.
    from dataclasses import replace

    events, state = _state_before_pick(1, 1)
    empty_pack_state = replace(state, seat_packs={})
    with pytest.raises(ValueError, match="no current pack"):
        build_agent_view(events, empty_pack_state, 0, _CATALOG, _FORMAT)
