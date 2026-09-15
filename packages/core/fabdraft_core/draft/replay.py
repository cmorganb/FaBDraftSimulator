"""Deterministic replay of a recorded draft session (plan section 7, WP-12).

Scope: this module is the core replay *mechanism*. A future `fabdraft
replay runs/{id}` CLI command (WP-17, `apps/cli` - not built here, still an
empty placeholder) will call into this.

Merely re-folding an existing event log (`fabdraft_core.draft.state.
fold_draft_events`, WP-07) proves nothing about determinism regressions: it
only replays already-recorded facts, never re-invoking any of the seeded
generation logic (pack sampling, shuffling, pass rotation, timeout
handling). Real replay means re-running `fabdraft_core.draft.engine.
run_draft` with the same seed and a pick source that reproduces the
originally recorded decisions, then comparing the freshly generated event
log against the original - that comparison is what would actually catch a
real regression (plan's own acceptance criterion: "a deliberate engine
change that breaks determinism fails the golden test").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fabdraft_core.contracts import Card, DraftEvent, PackConfig
from fabdraft_core.draft.engine import run_draft
from fabdraft_core.draft.events import EventStore
from fabdraft_core.draft.state import DraftState

_PICK_EVENT_TYPES = ("PICK_MADE", "PICK_AUTO")


# A sentinel `get_pick` can return to reproduce a *recorded* "invalid
# decision" timeout (plan section 8.1's `reason: invalid_decision`) -
# guaranteed to never collide with a real uid, so the engine's own
# `raw_pick in offered_uids` check correctly treats it as invalid again,
# taking the exact same PICK_AUTO path as the original run.
_INVALID_DECISION_SENTINEL = "__replay_invalid_decision__"


@dataclass
class RecordedPickSource:
    """A `fabdraft_core.draft.engine.PickSource` that replays previously
    recorded decisions instead of deciding live - the mechanism that lets a
    session be replayed "bit for bit" (plan section 7) regardless of what
    originally produced the picks (a human, a heuristic, an LLM, or a test
    double). `run_draft` calls `get_pick` for a given seat exactly once per
    (round, pick_number), always in increasing order - so the Nth call for
    a seat corresponds exactly to the Nth recorded pick for that seat,
    without needing round/pick_number as an explicit argument (the
    `PickSource` protocol doesn't pass them).

    A pick that was originally a `PICK_AUTO` (timeout/invalid decision, not
    a normal answer) must **not** simply be fed back as the recorded uid -
    that would make the engine treat it as an on-time `PICK_MADE` this
    time, changing the event type and breaking byte-for-byte replay. So a
    `no_response` auto-pick replays as `None` and an `invalid_decision`
    auto-pick replays as `_INVALID_DECISION_SENTINEL`; in both cases the
    engine's own `auto_pick` callable re-derives the *same* uid
    deterministically (identical seed, round, pick_number, seat, and
    offered pack), reproducing the original `PICK_AUTO` event exactly.
    """

    picks_by_seat: dict[int, list[tuple[str | None, bool, str | None]]]
    _next_index: dict[int, int] = field(default_factory=dict)

    async def get_pick(self, seat: int, pack: list[Card], deadline_ms: int | None) -> str | None:
        idx = self._next_index.get(seat, 0)
        picks = self.picks_by_seat.get(seat, [])
        if idx >= len(picks):
            return None
        self._next_index[seat] = idx + 1
        picked_uid, was_auto, reason = picks[idx]
        if not was_auto:
            return picked_uid
        return None if reason == "no_response" else _INVALID_DECISION_SENTINEL


def recorded_pick_source_from_events(events: list[DraftEvent]) -> RecordedPickSource:
    """Builds a `RecordedPickSource` from a previously-recorded event log's
    own `PICK_MADE`/`PICK_AUTO` events - no need for the original pick
    *source*'s logic at all, just its recorded outputs.
    """
    by_seat: dict[int, list[tuple[int, int, str | None, bool, str | None]]] = {}
    for e in events:
        if e.type in _PICK_EVENT_TYPES and e.seat is not None:
            round_number = e.round if e.round is not None else 0
            pick_number = e.pick_number if e.pick_number is not None else 0
            was_auto = e.type == "PICK_AUTO"
            reason = e.payload.get("reason") if was_auto else None
            by_seat.setdefault(e.seat, []).append(
                (round_number, pick_number, e.payload["picked_uid"], was_auto, reason)
            )
    picks_by_seat = {
        seat: [(uid, was_auto, reason) for _round, _pick, uid, was_auto, reason in sorted(items)]
        for seat, items in by_seat.items()
    }
    return RecordedPickSource(picks_by_seat=picks_by_seat)


def _first_payload(events: list[DraftEvent], event_type: str) -> dict[str, Any] | None:
    return next((e.payload for e in events if e.type == event_type), None)


class ReplayError(ValueError):
    """Raised when an event log doesn't carry enough information to be
    replayed (missing SEED_SET/POD_SEATED) - fail loud, don't guess at a
    seed or pod size.
    """


async def replay(
    original_events: list[DraftEvent],
    cards: list[Card],
    pack_config: PackConfig,
    *,
    session_id: str | None = None,
) -> tuple[DraftState, EventStore]:
    """Re-runs `run_draft` against `original_events`' own seed/pod-size,
    using a `RecordedPickSource` built from those same events, and returns
    the freshly generated `(DraftState, EventStore)` - compare its events
    against `original_events` with `events_match` to verify "bit for bit"
    replay (plan section 7).
    """
    if not original_events:
        raise ReplayError("cannot replay an empty event log")

    seed_payload = _first_payload(original_events, "SEED_SET")
    pod_payload = _first_payload(original_events, "POD_SEATED")
    if seed_payload is None or pod_payload is None:
        raise ReplayError(
            "cannot replay: original events have no SEED_SET/POD_SEATED "
            "(never infer a seed or pod size - fail loud instead)"
        )
    seed = str(seed_payload["seed"])
    pod_size = int(pod_payload["pod_size"])
    rounds = max((e.round for e in original_events if e.round is not None), default=0)
    sid = session_id if session_id is not None else original_events[0].session_id

    pick_source = recorded_pick_source_from_events(original_events)
    return await run_draft(
        session_id=sid,
        seed=seed,
        cards=cards,
        pack_config=pack_config,
        pick_source=pick_source,
        pod_size=pod_size,
        rounds=rounds,
    )


def _strip_wall_time(event: DraftEvent) -> dict[str, Any]:
    """`ts_wall` is real wall-clock time and legitimately differs between
    the original run and any later replay - excluded from comparison, same
    as `packages/core/tests/test_draft_engine.py`'s own determinism test.
    """
    d = event.model_dump(mode="json", by_alias=True)
    d.pop("ts_wall")
    return d


def events_match(events_a: list[DraftEvent], events_b: list[DraftEvent]) -> bool:
    """True iff two event logs are identical modulo `ts_wall` - the
    "bit for bit" comparison the plan's acceptance criterion asks for."""
    if len(events_a) != len(events_b):
        return False
    return all(
        _strip_wall_time(a) == _strip_wall_time(b) for a, b in zip(events_a, events_b, strict=True)
    )


def first_mismatch(
    events_a: list[DraftEvent], events_b: list[DraftEvent]
) -> tuple[int, dict[str, Any] | None, dict[str, Any] | None] | None:
    """Returns `(index, a_dict_or_None, b_dict_or_None)` for the first
    point of disagreement (ignoring `ts_wall`), or None if the logs match -
    useful for diagnosing *why* a replay diverged, not just *that* it did.
    """
    a_stripped = [_strip_wall_time(e) for e in events_a]
    b_stripped = [_strip_wall_time(e) for e in events_b]
    for i in range(max(len(a_stripped), len(b_stripped))):
        a = a_stripped[i] if i < len(a_stripped) else None
        b = b_stripped[i] if i < len(b_stripped) else None
        if a != b:
            return i, a, b
    return None
