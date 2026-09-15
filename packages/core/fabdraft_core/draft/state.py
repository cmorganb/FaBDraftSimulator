"""Pure draft state and its event reducer (plan section 4.1 item 1: "the
draft is an append-only event log; all state is a pure fold over events").

Card *identity* (uid + which slot/pack it came from) is tracked here;
resolving a uid to full `Card` data (name, text, rarity, ...) is left to
whoever's rendering a view (WP-08) or a log (WP-11) - that's static catalog
data, not part of the event-sourced state, so state and events stay small
and serialization-cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from fabdraft_core.contracts import DraftEvent
from fabdraft_core.draft.events import fold

Phase = Literal["not_started", "drafting", "reviewing", "finished"]


@dataclass(frozen=True)
class CardRef:
    """One card as tracked by draft state - just enough to reconstruct pack
    contents and draftability without embedding full Card data.
    """

    uid: str
    slot_id: str
    foiling: str | None
    draftable: bool


@dataclass(frozen=True)
class PackState:
    pack_id: str  # stable identity across passes, e.g. "r1p3" (round 1, opened by seat 3)
    cards: tuple[CardRef, ...]  # physical order, shrinks as cards are picked


@dataclass(frozen=True)
class DraftState:
    seed: str = ""
    pod_size: int = 8
    round: int = 0  # 0 = not started
    pick_number: int = 0  # 1..14 within a round
    phase: Phase = "not_started"
    seat_packs: dict[int, PackState] = field(default_factory=dict)
    seat_pools: dict[int, tuple[CardRef, ...]] = field(default_factory=dict)
    seat_extras: dict[int, tuple[CardRef, ...]] = field(default_factory=dict)
    timeout_count: int = 0


def _pack_id(round_number: int, origin_seat: int) -> str:
    return f"r{round_number}p{origin_seat}"


def draft_reducer(state: DraftState, event: DraftEvent) -> DraftState:
    payload = event.payload

    if event.type == "SEED_SET":
        return replace(state, seed=payload["seed"])

    if event.type == "POD_SEATED":
        pod_size = payload["pod_size"]
        return replace(
            state,
            pod_size=pod_size,
            seat_pools={seat: () for seat in range(pod_size)},
            seat_extras={seat: () for seat in range(pod_size)},
        )

    if event.type == "PACK_OPENED":
        seat = event.seat
        assert seat is not None
        refs = tuple(CardRef(**c) for c in payload["cards"])
        pack = PackState(pack_id=_pack_id(event.round or 0, seat), cards=refs)
        seat_packs = dict(state.seat_packs)
        seat_packs[seat] = pack
        return replace(
            state, round=event.round or state.round, phase="drafting", seat_packs=seat_packs
        )

    if event.type == "EXTRAS_REMOVED":
        seat = event.seat
        assert seat is not None
        removed_uids = set(payload["extras_uids"])
        pack = state.seat_packs[seat]
        remaining = tuple(c for c in pack.cards if c.uid not in removed_uids)
        removed = tuple(c for c in pack.cards if c.uid in removed_uids)
        seat_packs = dict(state.seat_packs)
        seat_packs[seat] = replace(pack, cards=remaining)
        seat_extras = dict(state.seat_extras)
        seat_extras[seat] = seat_extras.get(seat, ()) + removed
        return replace(state, seat_packs=seat_packs, seat_extras=seat_extras)

    if event.type == "PICK_WINDOW_OPENED":
        return replace(state, pick_number=event.pick_number or state.pick_number)

    if event.type in ("PICK_MADE", "PICK_AUTO"):
        seat = event.seat
        assert seat is not None
        picked_uid = payload["picked_uid"]
        pack = state.seat_packs[seat]
        picked = next(c for c in pack.cards if c.uid == picked_uid)
        remaining = tuple(c for c in pack.cards if c.uid != picked_uid)
        seat_packs = dict(state.seat_packs)
        seat_packs[seat] = replace(pack, cards=remaining)
        seat_pools = dict(state.seat_pools)
        seat_pools[seat] = seat_pools.get(seat, ()) + (picked,)
        timeout_count = state.timeout_count + (1 if event.type == "PICK_AUTO" else 0)
        return replace(
            state, seat_packs=seat_packs, seat_pools=seat_pools, timeout_count=timeout_count
        )

    if event.type == "PACK_SHUFFLED":
        seat = event.seat
        assert seat is not None
        new_order = payload["order_uids"]
        pack = state.seat_packs[seat]
        by_uid = {c.uid: c for c in pack.cards}
        reordered = tuple(by_uid[uid] for uid in new_order)
        seat_packs = dict(state.seat_packs)
        seat_packs[seat] = replace(pack, cards=reordered)
        return replace(state, seat_packs=seat_packs)

    if event.type == "PACK_PASSED":
        # Each PACK_PASSED event declares the pack a seat now holds, computed
        # by the engine from a single pre-pass snapshot - see engine.py. This
        # keeps the reducer trivial and avoids any cross-seat ordering
        # dependency (no "move" semantics to get wrong).
        seat = event.seat
        assert seat is not None
        pack_data = payload["pack"]
        pack = PackState(
            pack_id=pack_data["pack_id"],
            cards=tuple(CardRef(**c) for c in pack_data["cards"]),
        )
        seat_packs = dict(state.seat_packs)
        seat_packs[seat] = pack
        return replace(state, seat_packs=seat_packs)

    if event.type == "ROUND_COMPLETE":
        return replace(state, seat_packs={}, pick_number=0)

    if event.type == "REVIEW_OPENED":
        return replace(state, phase="reviewing")

    if event.type == "REVIEW_CLOSED":
        return replace(state, phase="drafting")

    if event.type == "POOL_FINALIZED":
        return replace(state, phase="finished")

    return state


def fold_draft_events(events: list[DraftEvent]) -> DraftState:
    return fold(events, draft_reducer, DraftState())
