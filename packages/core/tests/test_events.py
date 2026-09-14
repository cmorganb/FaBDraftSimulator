"""Tests for the append-only event store and fold mechanism (WP-04)."""

from __future__ import annotations

from fabdraft_core.contracts import DraftEvent
from fabdraft_core.draft.events import EventStore, fold
from hypothesis import given
from hypothesis import strategies as st

_EVENT_TYPES = [
    "SESSION_CREATED",
    "SEED_SET",
    "POD_SEATED",
    "PACK_OPENED",
    "PICK_MADE",
    "PICK_AUTO",
    "ROUND_COMPLETE",
]

_EMPTY_COUNTS: dict[str, int] = {}


def _event(event_id: int, type_: str, seat: int | None = None) -> DraftEvent:
    return DraftEvent(
        event_id=event_id,
        session_id="s1",
        ts_sim_ms=event_id * 100,
        ts_wall="2026-09-14T00:00:00Z",  # type: ignore[arg-type]
        type=type_,  # type: ignore[arg-type]
        round=None,
        pick_number=None,
        seat=seat,
        payload={},
    )


def _count_by_type(counts: dict[str, int], event: DraftEvent) -> dict[str, int]:
    """A synthetic reducer, standing in for WP-07's real DraftState reducer."""
    new_counts = dict(counts)
    new_counts[event.type] = new_counts.get(event.type, 0) + 1
    return new_counts


def test_event_store_append_and_events_property() -> None:
    store = EventStore()
    store.append(_event(1, "SESSION_CREATED"))
    store.append(_event(2, "SEED_SET"))
    assert len(store) == 2
    assert [e.type for e in store.events] == ["SESSION_CREATED", "SEED_SET"]


def test_events_property_returns_a_copy_not_a_live_reference() -> None:
    store = EventStore()
    store.append(_event(1, "SESSION_CREATED"))
    snapshot = store.events
    store.append(_event(2, "SEED_SET"))
    assert len(snapshot) == 1
    assert len(store.events) == 2


def test_fold_is_a_pure_left_fold_over_events() -> None:
    events = [
        _event(1, "SESSION_CREATED"),
        _event(2, "PICK_MADE", seat=0),
        _event(3, "PICK_MADE", seat=1),
        _event(4, "PICK_MADE", seat=0),
    ]
    result = fold(events, _count_by_type, _EMPTY_COUNTS)
    assert result == {"SESSION_CREATED": 1, "PICK_MADE": 3}


def test_folding_the_same_log_twice_yields_identical_state() -> None:
    store = EventStore()
    for i, t in enumerate(
        ["SESSION_CREATED", "SEED_SET", "POD_SEATED", "PACK_OPENED", "PICK_MADE"], start=1
    ):
        store.append(_event(i, t))

    result_1 = store.fold(_count_by_type, _EMPTY_COUNTS)
    result_2 = store.fold(_count_by_type, _EMPTY_COUNTS)
    assert result_1 == result_2
    # And folding a fresh, independently-built copy of the same events
    # produces the same result too - this is what makes replay (WP-12) work.
    result_3 = fold(store.events, _count_by_type, _EMPTY_COUNTS)
    assert result_1 == result_3


def test_fold_over_empty_events_returns_initial_state_unchanged() -> None:
    assert fold([], _count_by_type, _EMPTY_COUNTS) == _EMPTY_COUNTS


@given(
    st.lists(
        st.tuples(st.integers(min_value=1, max_value=10_000), st.sampled_from(_EVENT_TYPES)),
        max_size=50,
    )
)
def test_property_folding_the_same_events_twice_is_always_identical(
    pairs: list[tuple[int, str]],
) -> None:
    events = [_event(i, t) for i, t in pairs]
    result_a = fold(events, _count_by_type, _EMPTY_COUNTS)
    result_b = fold(events, _count_by_type, _EMPTY_COUNTS)
    assert result_a == result_b
