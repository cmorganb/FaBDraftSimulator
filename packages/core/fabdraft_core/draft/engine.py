"""The booster draft state machine (plan section 6.2, WP-07).

# TRP 8.2.1: "Each Player opens one of the draft product booster packs and
# removes the non-draftable card(s)... looks at their cards, drafts one
# card, places it face-down in a single pile in front of them, then
# shuffles the remaining cards and passes them to the Player on their
# left... repeat this process until all of the cards have been drafted."

`PickSource` below is a deliberately minimal, temporary seam: WP-08
(information policy) and WP-14 (agent protocol) don't exist yet, so this
engine can't accept a real `Agent` + `AgentView` pair. A pick source sees
only its own seat's current pack (already exactly what a rules-accurate
seat is allowed to see *during* a pack round - plan section 3.2 - so this
happens to be a safe subset of the eventual AgentView, just not the full
thing). WP-08/WP-14 will either adapt a real `Agent` into this shape or
replace this seam once they land.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from fabdraft_core.contracts import Card, DraftEvent, PackConfig
from fabdraft_core.draft.clock import Clock, SimClock
from fabdraft_core.draft.events import EventStore
from fabdraft_core.draft.pod import next_seat
from fabdraft_core.draft.state import CardRef, DraftState, draft_reducer
from fabdraft_core.draft.timers import REVIEW_WINDOW_SECONDS, timer_seconds_for_pack_size
from fabdraft_core.packs.generator import Pack, PackedCard, generate_pack
from fabdraft_core.rng import SeededRng, rng_for


class PickSource(Protocol):
    async def get_pick(self, seat: int, pack: list[Card], deadline_ms: int | None) -> str | None:
        """Return a uid present in `pack`, or None to decline / time out.
        A non-None return that isn't actually in `pack` is treated exactly
        like a decline (plan section 8.1: "The engine rejects a decision
        whose picked_uid is not in the presented pack and treats rejection
        as a timeout").
        """
        ...


AutoPickPolicy = Callable[[list[CardRef], SeededRng], str]


def random_auto_pick(candidates: list[CardRef], rng: SeededRng) -> str:
    """plan section 3.3's `timeout_policy: random`. `heuristic_best` needs a
    real heuristic agent (WP-15) and is not implemented here - pass a
    different `auto_pick` callable once one exists.
    """
    return rng.choice(candidates).uid


def _card_ref(pc: PackedCard) -> CardRef:
    return CardRef(uid=pc.card.uid, slot_id=pc.slot_id, foiling=pc.foiling, draftable=pc.draftable)


def _card_ref_dict(ref: CardRef) -> dict[str, Any]:
    return {
        "uid": ref.uid,
        "slot_id": ref.slot_id,
        "foiling": ref.foiling,
        "draftable": ref.draftable,
    }


def _resolve(refs: tuple[CardRef, ...], catalog: dict[str, Card]) -> list[Card]:
    return [catalog[r.uid] for r in refs]


class _EventBuilder:
    def __init__(self, session_id: str, clock: Clock) -> None:
        self._session_id = session_id
        self._clock = clock
        self._next_id = 0

    def build(
        self,
        event_type: str,
        *,
        round_number: int | None = None,
        pick_number: int | None = None,
        seat: int | None = None,
        payload: dict[str, Any],
    ) -> DraftEvent:
        event = DraftEvent.model_validate(
            {
                "event_id": self._next_id,
                "session_id": self._session_id,
                "ts_sim_ms": self._clock.now_ms(),
                "ts_wall": datetime.now(UTC).isoformat(),
                "type": event_type,
                "round": round_number,
                "pick_number": pick_number,
                "seat": seat,
                "payload": payload,
            }
        )
        self._next_id += 1
        return event


async def run_draft(
    session_id: str,
    seed: str,
    cards: list[Card],
    pack_config: PackConfig,
    pick_source: PickSource,
    *,
    pod_size: int = 8,
    rounds: int = 3,
    clock: Clock | None = None,
    event_store: EventStore | None = None,
    auto_pick: AutoPickPolicy = random_auto_pick,
    review_window_seconds: int = REVIEW_WINDOW_SECONDS,
    skip_review: bool = True,
) -> tuple[DraftState, EventStore]:
    """Runs a full booster draft (plan section 6.2) and returns the final
    `DraftState` plus the complete `EventStore` (every event is also
    replayable via `fold_draft_events` for WP-12).
    """
    clock = clock or SimClock()
    event_store = event_store or EventStore()
    events = _EventBuilder(session_id, clock)
    catalog = {c.uid: c for c in cards}
    picks_per_round = sum(s.count for s in pack_config.slots if s.draftable)

    def emit(event: DraftEvent) -> None:
        event_store.append(event)

    state = DraftState()

    session_created = events.build("SESSION_CREATED", payload={"session_id": session_id})
    emit(session_created)
    state = draft_reducer(state, session_created)

    seed_event = events.build("SEED_SET", payload={"seed": seed})
    emit(seed_event)
    state = draft_reducer(state, seed_event)

    pod_event = events.build("POD_SEATED", payload={"pod_size": pod_size})
    emit(pod_event)
    state = draft_reducer(state, pod_event)

    for round_number in range(1, rounds + 1):
        for seat in range(pod_size):
            pack_rng = rng_for(seed, "pack", round_number, seat)
            pack: Pack = generate_pack(cards, pack_config, pack_rng)
            refs = [_card_ref(pc) for pc in pack.cards]
            event = events.build(
                "PACK_OPENED",
                round_number=round_number,
                seat=seat,
                payload={"cards": [_card_ref_dict(r) for r in refs]},
            )
            emit(event)
            state = draft_reducer(state, event)

            extras_uids = [r.uid for r in refs if not r.draftable]
            extras_event = events.build(
                "EXTRAS_REMOVED",
                round_number=round_number,
                seat=seat,
                payload={"extras_uids": extras_uids},
            )
            emit(extras_event)
            state = draft_reducer(state, extras_event)

        for pick_number in range(1, picks_per_round + 1):
            pack_size = picks_per_round - pick_number + 1
            timer_seconds = timer_seconds_for_pack_size(pack_size)
            timer_event = events.build(
                "PICK_WINDOW_OPENED",
                round_number=round_number,
                pick_number=pick_number,
                payload={"time_limit_ms": None if timer_seconds is None else timer_seconds * 1000},
            )
            emit(timer_event)
            state = draft_reducer(state, timer_event)

            deadline_ms = (
                None if timer_seconds is None else clock.now_ms() + int(timer_seconds * 1000)
            )
            offered_by_seat = {
                seat: _resolve(state.seat_packs[seat].cards, catalog) for seat in range(pod_size)
            }

            async def _get(
                seat: int,
                offered: dict[int, list[Card]] = offered_by_seat,
                deadline: int | None = deadline_ms,
                timer: float | None = timer_seconds,
            ) -> str | None:
                return await clock.resolve_pick(
                    pick_source.get_pick(seat, offered[seat], deadline), timer
                )

            raw_results = await asyncio.gather(*[_get(seat) for seat in range(pod_size)])

            # A called draft's timer runs for its full recommended duration
            # regardless of how quickly pick sources actually respond (TRP
            # A.3; plan section 2.2's 360s/round derivation sums these
            # nominal durations) - advance the simulated clock accordingly
            # before recording the outcome.
            if timer_seconds is not None:
                await clock.advance_ms(int(timer_seconds * 1000))

            for seat, raw_pick in zip(range(pod_size), raw_results, strict=True):
                pack_state = state.seat_packs[seat]
                offered_uids = {r.uid for r in pack_state.cards}
                if raw_pick is not None and raw_pick in offered_uids:
                    event = events.build(
                        "PICK_MADE",
                        round_number=round_number,
                        pick_number=pick_number,
                        seat=seat,
                        payload={
                            "pack_id": pack_state.pack_id,
                            "pack_size_before": len(pack_state.cards),
                            "offered_uids": sorted(offered_uids),
                            "picked_uid": raw_pick,
                            "timed_out": False,
                        },
                    )
                else:
                    rng = rng_for(seed, "autopick", round_number, pick_number, seat)
                    picked_uid = auto_pick(list(pack_state.cards), rng)
                    reason = "no_response" if raw_pick is None else "invalid_decision"
                    event = events.build(
                        "PICK_AUTO",
                        round_number=round_number,
                        pick_number=pick_number,
                        seat=seat,
                        payload={
                            "pack_id": pack_state.pack_id,
                            "pack_size_before": len(pack_state.cards),
                            "offered_uids": sorted(offered_uids),
                            "picked_uid": picked_uid,
                            "timed_out": True,
                            "reason": reason,
                        },
                    )
                emit(event)
                state = draft_reducer(state, event)

            for seat in range(pod_size):
                pack_state = state.seat_packs[seat]
                if not pack_state.cards:
                    continue
                shuffle_rng = rng_for(seed, "shuffle", round_number, pick_number, seat)
                shuffled = shuffle_rng.shuffle(list(pack_state.cards))
                event = events.build(
                    "PACK_SHUFFLED",
                    round_number=round_number,
                    pick_number=pick_number,
                    seat=seat,
                    payload={"order_uids": [c.uid for c in shuffled]},
                )
                emit(event)
                state = draft_reducer(state, event)

            if pick_number < picks_per_round:
                pre_pass_packs = dict(state.seat_packs)
                for seat in range(pod_size):
                    pack_state = pre_pass_packs[seat]
                    if not pack_state.cards:
                        continue
                    receiver = next_seat(seat, round_number, pod_size)
                    event = events.build(
                        "PACK_PASSED",
                        round_number=round_number,
                        pick_number=pick_number,
                        seat=receiver,
                        payload={
                            "from_seat": seat,
                            "pack": {
                                "pack_id": pack_state.pack_id,
                                "cards": [_card_ref_dict(c) for c in pack_state.cards],
                            },
                        },
                    )
                    emit(event)
                    state = draft_reducer(state, event)

        round_event = events.build("ROUND_COMPLETE", round_number=round_number, payload={})
        emit(round_event)
        state = draft_reducer(state, round_event)

        review_opened = events.build(
            "REVIEW_OPENED",
            round_number=round_number,
            payload={"window_seconds": review_window_seconds, "skipped": skip_review},
        )
        emit(review_opened)
        state = draft_reducer(state, review_opened)
        if not skip_review:
            await clock.advance_ms(review_window_seconds * 1000)
        review_closed = events.build("REVIEW_CLOSED", round_number=round_number, payload={})
        emit(review_closed)
        state = draft_reducer(state, review_closed)

    finalized = events.build(
        "POOL_FINALIZED",
        # A pod-wide aggregate only - never a per-seat breakdown, so this
        # event can never look like it's exposing another seat's pool.
        payload={"total_drafted": sum(len(pool) for pool in state.seat_pools.values())},
    )
    emit(finalized)
    state = draft_reducer(state, finalized)

    return state, event_store
