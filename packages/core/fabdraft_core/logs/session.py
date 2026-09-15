"""session.json writer (plan section 7, WP-11): "metadata index for search:
seed, timestamps, seat agents, per-seat hero, deck validity, counts,
cost/token usage for LLM seats."

Same I/O exception as `fabdraft_core.logs.jsonl`/`markdown` (plan section
4.1 item 2 - logging is an injected port). Fields with no producing WP yet
(seat agents beyond what the caller supplies, per-seat hero, deck validity,
LLM cost/token usage - see `fabdraft_core.logs.markdown`'s module docstring
for why) are populated as `None`/empty rather than fabricated.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fabdraft_core.contracts import DraftEvent


def build_session_summary(
    events: Sequence[DraftEvent],
    *,
    seat_labels: Mapping[int, str] | None = None,
) -> dict[str, Any]:
    if not events:
        return {
            "session_id": None,
            "seed": None,
            "pod_size": None,
            "started_at": None,
            "ended_at": None,
            "total_picks": 0,
            "timeout_counts": {},
            "seat_agents": dict(seat_labels or {}),
            "per_seat_hero": {},
            "deck_validity": {},
            "llm_cost_usage": {},
        }

    session_id = events[0].session_id
    seed_payload = next((e.payload for e in events if e.type == "SEED_SET"), None)
    pod_payload = next((e.payload for e in events if e.type == "POD_SEATED"), None)

    timeout_counts: dict[int, int] = {}
    total_picks = 0
    for e in events:
        if e.type in ("PICK_MADE", "PICK_AUTO"):
            total_picks += 1
            if e.type == "PICK_AUTO" and e.seat is not None:
                timeout_counts[e.seat] = timeout_counts.get(e.seat, 0) + 1

    # HERO_SELECTED / VALIDATION_RESULT: no deck-build orchestrator emits
    # these yet (see fabdraft_core.logs.markdown's docstring) - populated
    # only if present, never guessed.
    per_seat_hero = {e.seat: e.payload.get("hero_uid") for e in events if e.type == "HERO_SELECTED"}
    deck_validity = {
        e.seat: e.payload.get("valid") for e in events if e.type == "VALIDATION_RESULT"
    }

    return {
        "session_id": session_id,
        "seed": seed_payload["seed"] if seed_payload else None,
        "pod_size": pod_payload["pod_size"] if pod_payload else None,
        "started_at": events[0].ts_wall.isoformat(),
        "ended_at": events[-1].ts_wall.isoformat(),
        "total_picks": total_picks,
        "timeout_counts": timeout_counts,
        "seat_agents": dict(seat_labels or {}),
        "per_seat_hero": per_seat_hero,
        "deck_validity": deck_validity,
        "llm_cost_usage": {},  # no LLM agent exists yet (WP-16)
    }


def write_session_json(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
