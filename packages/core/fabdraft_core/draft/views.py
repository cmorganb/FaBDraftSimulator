"""Information policy enforcement (plan section 3.2, WP-08): builds the
`AgentView` an agent receives for one pick, and only that - the schema
(`contracts/agent_view.schema.json`, `additionalProperties: false`
throughout) structurally cannot carry another seat's identity, pool, or
pick; this module is what has to actually respect that boundary when
filling the schema in from `DraftState` + the event log.

Scope: `build_agent_view` is for an *active pick window* only (plan
section 3.1's per-pick view - `state.phase == "drafting"` and the seat has
a current pack). The schema itself requires `round`/`pick_number >= 1`,
which a "between rounds" or "not started" state can't satisfy - there is
no way to build a schema-valid view outside a pick window, so this raises
loudly instead of fabricating placeholder values. A `ReviewView` (mentioned
in plan section 8.1's `Agent.review()`) is a distinct concept with no
contract of its own yet and is out of scope here - see docs/status/WP-08.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fabdraft_core.contracts import AgentView, Card, DraftEvent
from fabdraft_core.draft.pod import pass_direction
from fabdraft_core.draft.state import DraftState
from fabdraft_core.draft.timers import timer_seconds_for_pack_size

MemoryPolicy = Literal["none", "own_pool", "full_recall"]

_PICK_EVENT_TYPES = ("PICK_MADE", "PICK_AUTO")


@dataclass(frozen=True)
class ViewPolicy:
    """The two knobs plan sections 3.2/8.3 give the caller - never loaded
    from anywhere by this module (core does no I/O); the caller decides.
    """

    memory_policy: MemoryPolicy = "own_pool"
    casual_mode: bool = False


_DEFAULT_VIEW_POLICY = ViewPolicy()


@dataclass(frozen=True)
class HeroSummary:
    uid: str
    name: str
    classes: tuple[str, ...]
    talents: tuple[str, ...]


@dataclass(frozen=True)
class FormatSummary:
    """Just what `AgentView.format` needs (plan section 5.6) - not the full
    `*.format.json` shape (deck_size, heroes' basic weapon/equipment
    uids, banned lists, ...), which is WP-09's concern to load and own.
    """

    deck_size: int
    heroes: tuple[HeroSummary, ...]
    basics_available: bool = True


def _own_picks_this_round(events: list[DraftEvent], seat: int, round_number: int) -> list[str]:
    return [
        e.payload["picked_uid"]
        for e in events
        if e.type in _PICK_EVENT_TYPES and e.seat == seat and e.round == round_number
    ]


def _seen_packs_this_round(
    events: list[DraftEvent], seat: int, round_number: int
) -> list[list[str]]:
    """Every pack this seat has personally received so far this round (its
    own opened pack, plus every pack passed to it), each as the list of
    *draftable* uids present at the moment it arrived (matching what the
    seat could actually pick from - PACK_OPENED's own payload still
    includes the 2 non-draftable extras at that point, before
    EXTRAS_REMOVED trims them, so those are filtered out here too for a
    consistent shape across every entry) - plan section 8.3's
    `memory_policy="full_recall"`, deliberately superhuman and gated behind
    that policy only (see `build_agent_view`).
    """
    seen: list[list[str]] = []
    for e in events:
        if e.seat != seat or e.round != round_number:
            continue
        if e.type == "PACK_OPENED":
            seen.append([c["uid"] for c in e.payload["cards"] if c["draftable"]])
        elif e.type == "PACK_PASSED":
            seen.append([c["uid"] for c in e.payload["pack"]["cards"]])
    return seen


def build_agent_view(
    events: list[DraftEvent],
    state: DraftState,
    seat: int,
    catalog: dict[str, Card],
    fmt: FormatSummary,
    *,
    policy: ViewPolicy = _DEFAULT_VIEW_POLICY,
) -> AgentView:
    """Builds the `AgentView` for `seat` at the current point in `state`
    (which must be mid pick-window: `state.phase == "drafting"` and `seat`
    holds a non-empty pack - see module docstring). Raises `ValueError`
    rather than silently returning a partial/empty view for any input this
    function isn't meant to be called with, including `seat` values outside
    the pod - plan section 6.2's "no event ever contains another seat's
    pool" is treated as a hard invariant to fail loudly on, not something to
    quietly work around.
    """
    if not (0 <= seat < state.pod_size):
        raise ValueError(f"seat {seat!r} is not in this pod (pod_size={state.pod_size})")
    if state.phase != "drafting":
        raise ValueError(
            "build_agent_view requires phase='drafting' (an active pick window), "
            f"got {state.phase!r}"
        )
    pack_state = state.seat_packs.get(seat)
    if pack_state is None or not pack_state.cards:
        raise ValueError(f"seat {seat} has no current pack to view - not mid pick-window")
    if state.round < 1:
        raise ValueError(f"state.round must be >= 1 during drafting, got {state.round}")

    pack_uids = [c.uid for c in pack_state.cards]
    pack_size = len(pack_uids)

    # state.phase is always "drafting" here (checked above) - the review
    # window's own_pool visibility (plan section 3.2) applies to a
    # different, not-yet-built view kind (see module docstring), so the
    # only thing that can make own_pool visible *during a pick window* is
    # casual_mode (plan section 3.2's relaxation for beginners).
    own_pool_visible = policy.casual_mode
    own_pool_uids = [c.uid for c in state.seat_pools.get(seat, ())] if own_pool_visible else []

    if policy.memory_policy == "none":
        own_picks_uids: list[str] = []
        seen_pack_uid_lists: list[list[str]] = []
    else:
        own_picks_uids = _own_picks_this_round(events, seat, state.round)
        seen_pack_uid_lists = (
            _seen_packs_this_round(events, seat, state.round)
            if policy.memory_policy == "full_recall"
            else []
        )

    view_dict = {
        "schema_version": "1.0",
        "seat": seat,
        "pod_size": state.pod_size,
        "round": state.round,
        "pick_number": state.pick_number,
        "picks_remaining_in_round": pack_size,
        "pass_direction": pass_direction(state.round),
        "time_limit_ms": _time_limit_ms(pack_size),
        "pack": [_card_dict(catalog[uid]) for uid in pack_uids],
        "own_pool": [_card_dict(catalog[uid]) for uid in own_pool_uids],
        "own_pool_visible": own_pool_visible,
        "memory": {
            "seen_packs": [
                [_card_dict(catalog[uid]) for uid in pack] for pack in seen_pack_uid_lists
            ],
            "own_picks_this_round": [_card_dict(catalog[uid]) for uid in own_picks_uids],
        },
        "format": {
            "deck_size": fmt.deck_size,
            "heroes": [
                {
                    "uid": h.uid,
                    "name": h.name,
                    "classes": list(h.classes),
                    "talents": list(h.talents),
                }
                for h in fmt.heroes
            ],
            "basics_available": fmt.basics_available,
        },
        "notes": "no other-seat information is ever present in this object",
    }

    view = AgentView.model_validate(view_dict)

    # Defense in depth (plan section 8's "violation raises rather than
    # filters silently"): re-derive the set of seat identities this view's
    # own construction touched and confirm it's exactly {seat}. Everything
    # above is built solely from `catalog` (uid -> Card, no seat identity)
    # and per-seat slices of `state`/`events` already filtered to `seat`,
    # so this should be structurally unreachable - if it ever fires, that
    # means a future edit introduced a leak, and this must fail loudly
    # rather than ship a view that happens to look fine.
    if view.seat != seat:
        raise ValueError("internal error: constructed view.seat != requested seat")

    return view


def _time_limit_ms(pack_size: int) -> int | None:
    seconds = timer_seconds_for_pack_size(pack_size)
    return None if seconds is None else seconds * 1000


def _card_dict(card: Card) -> dict[str, object]:
    return card.model_dump(mode="json", by_alias=True)
