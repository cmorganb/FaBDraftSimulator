"""Human-readable draft_log.md renderer (plan section 7, WP-11).

Like `fabdraft_core.logs.jsonl`, this module does real I/O (writing a
markdown file) - an intentional exception to `packages/core`'s general
purity rule, since logging is explicitly one of the plan's "injected
ports" (plan section 4.1 item 2).

Scope note: no agent (WP-14) or deck-build orchestrator (event emitter for
HERO_SELECTED/DECK_CARD_ADDED/DECK_CARD_REMOVED/DECK_SUBMITTED/
VALIDATION_RESULT) exists yet. This renderer reads whatever the given event
log actually contains: pick events never carry model/reasoning metadata
today (rendered only if present, never fabricated), and the "deck build
actions / validation result / final decklist" section of plan section 7
renders as explicitly pending when those event types are absent - not as
an empty or broken-looking section.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from fabdraft_core.contracts import Card, DraftEvent, PackConfig

_DECK_BUILD_EVENT_TYPES = (
    "HERO_SELECTED",
    "DECK_CARD_ADDED",
    "DECK_CARD_REMOVED",
    "DECK_SUBMITTED",
    "VALIDATION_RESULT",
)


def _card_summary(card: Card) -> str:
    bits = [card.name]
    if card.pitch is not None:
        bits.append(f"pitch {card.pitch}")
    bits.append(card.rarity)
    stats = [
        f"{label} {value}"
        for label, value in (("cost", card.cost), ("power", card.power), ("defense", card.defense))
        if value is not None
    ]
    if stats:
        bits.append("/".join(stats))
    return ", ".join(bits)


def _first_payload(events: Sequence[DraftEvent], event_type: str) -> dict[str, object] | None:
    for e in events:
        if e.type == event_type:
            return e.payload
    return None


def _session_header(
    events: Sequence[DraftEvent],
    *,
    seat_labels: Mapping[int, str] | None,
    casual_mode: bool,
    data_integrity: str,
    pack_config: PackConfig | None,
) -> list[str]:
    session_id = events[0].session_id if events else "(empty log)"
    seed_payload = _first_payload(events, "SEED_SET")
    pod_payload = _first_payload(events, "POD_SEATED")
    seed = seed_payload["seed"] if seed_payload else None
    pod_size = pod_payload["pod_size"] if pod_payload else None

    lines = [
        "# Draft Log",
        "",
        f"- **Session:** {session_id}",
        f"- **Seed:** {seed}",
        f"- **Pod size:** {pod_size}",
        f"- **Casual mode:** {casual_mode}",
        f"- **Data integrity:** {data_integrity}",
    ]
    if seat_labels:
        seats = ", ".join(f"seat {s}: {label}" for s, label in sorted(seat_labels.items()))
        lines.append(f"- **Seat configuration:** {seats}")
    else:
        lines.append("- **Seat configuration:** not provided")

    estimated_slots = [
        s.id for s in (pack_config.slots if pack_config else []) if s.confidence == "ESTIMATED"
    ]
    if estimated_slots:
        lines.append(
            "- **Estimated pack weights (unverified against real print-sheet odds):** "
            + ", ".join(estimated_slots)
        )
    lines.append("")
    return lines


def _pick_lines(
    events: Sequence[DraftEvent],
    round_number: int,
    pick_number: int,
    catalog: dict[str, Card],
    seat_labels: Mapping[int, str] | None,
) -> list[str]:
    pick_events = [
        e
        for e in events
        if e.type in ("PICK_MADE", "PICK_AUTO")
        and e.round == round_number
        and e.pick_number == pick_number
    ]
    if not pick_events:
        return []
    pack_size = pick_events[0].payload.get("pack_size_before")
    lines = [f"#### Pick {pick_number} (pack size {pack_size})", ""]
    for e in sorted(pick_events, key=lambda ev: ev.seat if ev.seat is not None else -1):
        seat = e.seat
        label = f"seat {seat}"
        if seat_labels and seat is not None and seat in seat_labels:
            label += f" ({seat_labels[seat]})"
        offered_uids = e.payload.get("offered_uids", [])
        offered = ", ".join(_card_summary(catalog[u]) for u in offered_uids if u in catalog)
        picked_uid = e.payload.get("picked_uid")
        picked = _card_summary(catalog[picked_uid]) if picked_uid in catalog else str(picked_uid)
        status = ""
        if e.payload.get("timed_out", False):
            reason = f", {e.payload['reason']}" if "reason" in e.payload else ""
            status = f" (TIMED OUT{reason})"
        lines.append(f"- **{label}** picked **{picked}**{status}")
        lines.append(f"  - Offered: {offered}")
        # Model reasoning/alternatives (plan section 7) - only ever rendered
        # when actually present; no agent exists yet (WP-14) so this is
        # always absent today, and that's expected, not a gap in this file.
        decision = e.payload.get("decision")
        if isinstance(decision, dict):
            agent = e.payload.get("agent", {})
            if agent:
                lines.append(f"  - Agent: {agent}")
            if "reasoning" in decision:
                lines.append(f"  - Reasoning: {decision['reasoning']}")
            if "ranked_alternatives" in decision:
                lines.append(f"  - Alternatives: {decision['ranked_alternatives']}")
    lines.append("")
    return lines


def _review_lines(events: Sequence[DraftEvent], round_number: int) -> list[str]:
    opened = next(
        (e for e in events if e.type == "REVIEW_OPENED" and e.round == round_number), None
    )
    if opened is None:
        return []
    window = opened.payload.get("window_seconds")
    skipped = opened.payload.get("skipped")
    return [f"**Review:** window {window}s, skipped={skipped}", ""]


def _deck_build_section(events: Sequence[DraftEvent]) -> list[str]:
    relevant = [e for e in events if e.type in _DECK_BUILD_EVENT_TYPES]
    lines = ["## Deck build", ""]
    if not relevant:
        lines.append(
            "_Pending: no deck-build events in this log (no orchestrator emits "
            "HERO_SELECTED/DECK_CARD_ADDED/DECK_CARD_REMOVED/DECK_SUBMITTED/"
            "VALIDATION_RESULT yet - WP-09 is a pure validator, not an event "
            "emitter). This section will populate once one exists._"
        )
        lines.append("")
        return lines
    for e in relevant:
        lines.append(f"- **{e.type}** (seat {e.seat}): {e.payload}")
    lines.append("")
    return lines


def render_draft_log(
    events: Sequence[DraftEvent],
    cards: Sequence[Card],
    *,
    seat_labels: Mapping[int, str] | None = None,
    casual_mode: bool = False,
    data_integrity: str = "complete",
    pack_config: PackConfig | None = None,
) -> str:
    """Renders the full plan section 7 narrative from a session's event
    log. `cards` is the set's full card catalog (used to resolve uids to
    name/pitch/rarity/cost/power/defense).
    """
    catalog = {c.uid: c for c in cards}
    lines = _session_header(
        events,
        seat_labels=seat_labels,
        casual_mode=casual_mode,
        data_integrity=data_integrity,
        pack_config=pack_config,
    )

    rounds = sorted(
        {e.round for e in events if e.round is not None and e.type != "SESSION_CREATED"}
    )
    for round_number in rounds:
        lines.append(f"## Round {round_number}")
        lines.append("")
        picks = sorted(
            {e.pick_number for e in events if e.round == round_number and e.pick_number is not None}
        )
        for pick_number in picks:
            lines.extend(_pick_lines(events, round_number, pick_number, catalog, seat_labels))
        lines.extend(_review_lines(events, round_number))

    finalized = _first_payload(events, "POOL_FINALIZED")
    if finalized is not None:
        lines.append(f"## Pool finalized: {finalized.get('total_drafted')} total cards drafted")
        lines.append("")

    lines.extend(_deck_build_section(events))

    return "\n".join(lines) + "\n"


def write_draft_log(path: Path, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
