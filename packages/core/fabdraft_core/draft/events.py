"""In-memory, append-only event store and fold-based state reconstruction
(plan section 4.1 item 1: "the draft is an append-only event log; all state
is a pure fold over events").

`EventStore` itself does no I/O (plan section 4.1 item 2) - persistence is
`fabdraft_core.logs.jsonl`'s job, called by an outer layer that owns the
event list this store produces.

The real `DraftState` reducer belongs to WP-07 (the draft engine doesn't
exist yet). This module proves the fold mechanism is pure and deterministic
using a generic `Reducer` type; WP-07 supplies the real one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from fabdraft_core.contracts import DraftEvent

type Reducer[State] = Callable[[State, DraftEvent], State]


class EventStore:
    """An append-only, in-memory sequence of DraftEvents."""

    def __init__(self) -> None:
        self._events: list[DraftEvent] = []

    def append(self, event: DraftEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[DraftEvent]:
        """A copy, so callers can't mutate the store's history in place."""
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def fold[State](self, reducer: Reducer[State], initial: State) -> State:
        return fold(self._events, reducer, initial)


def fold[State](events: Iterable[DraftEvent], reducer: Reducer[State], initial: State) -> State:
    """Pure left-fold over an event sequence: state = reducer(state, event)
    for each event, in order. Folding the same events with the same reducer
    and initial state always yields the same result - this is what makes
    replay (WP-12) possible.
    """
    state = initial
    for event in events:
        state = reducer(state, event)
    return state
