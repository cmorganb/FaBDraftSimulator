"""Unit tests for the draft event reducer (WP-07)."""

from __future__ import annotations

from typing import Any

from fabdraft_core.contracts import DraftEvent
from fabdraft_core.draft.state import CardRef, DraftState, draft_reducer, fold_draft_events


def _event(
    event_id: int,
    type_: str,
    *,
    round_number: int | None = None,
    pick_number: int | None = None,
    seat: int | None = None,
    payload: dict[str, Any],
) -> DraftEvent:
    return DraftEvent(
        event_id=event_id,
        session_id="s1",
        ts_sim_ms=event_id,
        ts_wall="2026-09-14T00:00:00Z",  # type: ignore[arg-type]
        type=type_,  # type: ignore[arg-type]
        round=round_number,
        pick_number=pick_number,
        seat=seat,
        payload=payload,
    )


def _card_dict(uid: str, *, draftable: bool = True) -> dict[str, Any]:
    return {"uid": uid, "slot_id": "common", "foiling": None, "draftable": draftable}


def test_seed_set_and_pod_seated_initialize_state() -> None:
    events = [
        _event(0, "SEED_SET", payload={"seed": "abc"}),
        _event(1, "POD_SEATED", payload={"pod_size": 8}),
    ]
    state = fold_draft_events(events)
    assert state.seed == "abc"
    assert state.pod_size == 8
    assert state.seat_pools == {s: () for s in range(8)}


def test_pack_opened_and_extras_removed() -> None:
    events = [
        _event(0, "POD_SEATED", payload={"pod_size": 2}),
        _event(
            1,
            "PACK_OPENED",
            round_number=1,
            seat=0,
            payload={
                "cards": [_card_dict("a"), _card_dict("b"), _card_dict("basic", draftable=False)]
            },
        ),
        _event(2, "EXTRAS_REMOVED", round_number=1, seat=0, payload={"extras_uids": ["basic"]}),
    ]
    state = fold_draft_events(events)
    assert [c.uid for c in state.seat_packs[0].cards] == ["a", "b"]
    assert [c.uid for c in state.seat_extras[0]] == ["basic"]
    assert state.seat_packs[0].pack_id == "r1p0"


def test_pick_made_moves_card_from_pack_to_pool() -> None:
    events = [
        _event(0, "POD_SEATED", payload={"pod_size": 1}),
        _event(
            1,
            "PACK_OPENED",
            round_number=1,
            seat=0,
            payload={"cards": [_card_dict("a"), _card_dict("b")]},
        ),
        _event(2, "PICK_MADE", round_number=1, pick_number=1, seat=0, payload={"picked_uid": "a"}),
    ]
    state = fold_draft_events(events)
    assert [c.uid for c in state.seat_packs[0].cards] == ["b"]
    assert [c.uid for c in state.seat_pools[0]] == ["a"]
    assert state.timeout_count == 0


def test_pick_auto_increments_timeout_count() -> None:
    events = [
        _event(0, "POD_SEATED", payload={"pod_size": 1}),
        _event(1, "PACK_OPENED", round_number=1, seat=0, payload={"cards": [_card_dict("a")]}),
        _event(2, "PICK_AUTO", round_number=1, pick_number=1, seat=0, payload={"picked_uid": "a"}),
    ]
    state = fold_draft_events(events)
    assert state.timeout_count == 1
    assert [c.uid for c in state.seat_pools[0]] == ["a"]


def test_pack_shuffled_reorders_without_changing_membership() -> None:
    events = [
        _event(0, "POD_SEATED", payload={"pod_size": 1}),
        _event(
            1,
            "PACK_OPENED",
            round_number=1,
            seat=0,
            payload={"cards": [_card_dict("a"), _card_dict("b"), _card_dict("c")]},
        ),
        _event(2, "PACK_SHUFFLED", round_number=1, seat=0, payload={"order_uids": ["c", "a", "b"]}),
    ]
    state = fold_draft_events(events)
    assert [c.uid for c in state.seat_packs[0].cards] == ["c", "a", "b"]


def test_pack_passed_replaces_the_seats_pack() -> None:
    events = [
        _event(0, "POD_SEATED", payload={"pod_size": 2}),
        _event(
            1,
            "PACK_PASSED",
            round_number=1,
            seat=1,
            payload={"from_seat": 0, "pack": {"pack_id": "r1p0", "cards": [_card_dict("x")]}},
        ),
    ]
    state = fold_draft_events(events)
    assert state.seat_packs[1].pack_id == "r1p0"
    assert [c.uid for c in state.seat_packs[1].cards] == ["x"]


def test_round_complete_clears_packs_but_keeps_pools() -> None:
    events = [
        _event(0, "POD_SEATED", payload={"pod_size": 1}),
        _event(1, "PACK_OPENED", round_number=1, seat=0, payload={"cards": [_card_dict("a")]}),
        _event(2, "PICK_MADE", round_number=1, pick_number=1, seat=0, payload={"picked_uid": "a"}),
        _event(3, "ROUND_COMPLETE", round_number=1, payload={}),
    ]
    state = fold_draft_events(events)
    assert state.seat_packs == {}
    assert [c.uid for c in state.seat_pools[0]] == ["a"]
    assert state.pick_number == 0


def test_review_and_pool_finalized_phase_transitions() -> None:
    events = [
        _event(0, "REVIEW_OPENED", round_number=1, payload={}),
    ]
    assert fold_draft_events(events).phase == "reviewing"
    events.append(_event(1, "REVIEW_CLOSED", round_number=1, payload={}))
    assert fold_draft_events(events).phase == "drafting"
    events.append(_event(2, "POOL_FINALIZED", payload={}))
    assert fold_draft_events(events).phase == "finished"


def test_unrecognized_event_type_is_a_no_op() -> None:
    initial = DraftState()
    event = _event(0, "SESSION_CREATED", payload={"session_id": "x"})
    assert draft_reducer(initial, event) == initial


def test_folding_the_same_events_twice_is_identical() -> None:
    events = [
        _event(0, "POD_SEATED", payload={"pod_size": 1}),
        _event(1, "PACK_OPENED", round_number=1, seat=0, payload={"cards": [_card_dict("a")]}),
        _event(2, "PICK_MADE", round_number=1, pick_number=1, seat=0, payload={"picked_uid": "a"}),
    ]
    assert fold_draft_events(events) == fold_draft_events(events)


def test_card_ref_is_a_plain_frozen_value() -> None:
    a = CardRef(uid="x", slot_id="common", foiling=None, draftable=True)
    b = CardRef(uid="x", slot_id="common", foiling=None, draftable=True)
    assert a == b
