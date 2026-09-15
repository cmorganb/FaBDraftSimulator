#!/usr/bin/env python3
"""Generate the golden draft event log used by WP-12's replay regression
test (plan section 4.3 names `data/fixtures/golden/` explicitly for this).

Runs one full, deterministic draft against the synthetic `FIXTURE` set and
saves its complete `events.jsonl` - `packages/core/tests/test_replay.py`
replays this log via `fabdraft_core.draft.replay.replay` and asserts the
freshly generated events match it exactly (modulo `ts_wall`). If this
script is ever re-run, the golden file changes and the replay test still
passes as long as the engine is genuinely still deterministic - the test's
value is in catching a *future* regression against whatever is currently
committed, not in pinning one eternal seed.

Usage:
    uv run python scripts/generate_golden_replay.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fabdraft_core.contracts import Card, PackConfig, SetSnapshot
from fabdraft_core.draft.engine import run_draft
from fabdraft_core.logs.jsonl import append_events

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SET_PATH = REPO_ROOT / "data" / "fixtures" / "fixture_set.json"
FIXTURE_PACK_CONFIG_PATH = REPO_ROOT / "data" / "config" / "fixture.pack_config.json"
GOLDEN_PATH = REPO_ROOT / "data" / "fixtures" / "golden" / "fixture_draft_events.jsonl"

GOLDEN_SEED = "golden-replay-seed-1"
GOLDEN_SESSION_ID = "golden-fixture-draft"


class FirstAvailablePickSource:
    """Deterministic, no randomness of its own - same pattern used
    throughout `packages/core/tests/test_draft_engine.py`.
    """

    async def get_pick(self, seat: int, pack: list[Card], deadline_ms: int | None) -> str | None:
        return pack[0].uid


async def main() -> None:
    cards = SetSnapshot.model_validate(json.loads(FIXTURE_SET_PATH.read_text())).cards
    pack_config = PackConfig.model_validate(json.loads(FIXTURE_PACK_CONFIG_PATH.read_text()))

    _state, store = await run_draft(
        session_id=GOLDEN_SESSION_ID,
        seed=GOLDEN_SEED,
        cards=cards,
        pack_config=pack_config,
        pick_source=FirstAvailablePickSource(),
    )

    if GOLDEN_PATH.exists():
        GOLDEN_PATH.unlink()
    append_events(GOLDEN_PATH, store.events)
    print(f"Wrote {len(store.events)} events to {GOLDEN_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
