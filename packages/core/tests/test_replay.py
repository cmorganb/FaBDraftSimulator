"""Tests for deterministic replay (WP-12, plan section 7).

The golden-file test is the WP's own acceptance criterion: "Replaying a
golden log reproduces byte-identical events; a deliberate engine change
that breaks determinism fails the golden test." `data/fixtures/golden/
fixture_draft_events.jsonl` is produced by `scripts/generate_golden_replay.py`
and committed - if a future engine change breaks determinism, replaying it
here will diverge from the committed events and this test will fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fabdraft_core.contracts import Card, PackConfig, SetSnapshot
from fabdraft_core.draft.engine import run_draft
from fabdraft_core.draft.replay import (
    RecordedPickSource,
    ReplayError,
    events_match,
    first_mismatch,
    recorded_pick_source_from_events,
    replay,
)
from fabdraft_core.logs.jsonl import read_events

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_SET_PATH = REPO_ROOT / "data" / "fixtures" / "fixture_set.json"
FIXTURE_PACK_CONFIG_PATH = REPO_ROOT / "data" / "config" / "fixture.pack_config.json"
GOLDEN_PATH = REPO_ROOT / "data" / "fixtures" / "golden" / "fixture_draft_events.jsonl"


@pytest.fixture(scope="module")
def fixture_cards() -> list[Card]:
    return SetSnapshot.model_validate(json.loads(FIXTURE_SET_PATH.read_text())).cards


@pytest.fixture(scope="module")
def fixture_pack_config() -> PackConfig:
    return PackConfig.model_validate(json.loads(FIXTURE_PACK_CONFIG_PATH.read_text()))


class FirstAvailablePickSource:
    async def get_pick(self, seat: int, pack: list[Card], deadline_ms: int | None) -> str | None:
        return pack[0].uid


class AlwaysTimesOutPickSource:
    async def get_pick(self, seat: int, pack: list[Card], deadline_ms: int | None) -> str | None:
        return None


async def test_golden_replay_reproduces_the_committed_log_exactly(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    golden_events = read_events(GOLDEN_PATH)
    assert len(golden_events) > 0

    _state, store = await replay(golden_events, fixture_cards, fixture_pack_config)

    assert events_match(golden_events, store.events)


async def test_replay_matches_a_freshly_generated_log_including_timeouts(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    """Not just the one committed golden fixture: any recorded log,
    including one produced via the PICK_AUTO/timeout path, should replay
    identically - proving the mechanism generalizes, not just the golden
    file's own happy path.
    """
    _orig_state, orig_store = await run_draft(
        session_id="fresh-replay-test",
        seed="fresh-replay-seed",
        cards=fixture_cards,
        pack_config=fixture_pack_config,
        pick_source=AlwaysTimesOutPickSource(),
    )

    _replay_state, replay_store = await replay(
        orig_store.events, fixture_cards, fixture_pack_config
    )

    assert events_match(orig_store.events, replay_store.events)


def test_events_match_detects_a_tampered_event(fixture_cards: list[Card]) -> None:
    """Proves the comparison itself can tell 'identical' from 'different' -
    the golden test above is only meaningful if this is true."""
    golden_events = read_events(GOLDEN_PATH)
    tampered = list(golden_events)
    pick_index = next(i for i, e in enumerate(tampered) if e.type == "PICK_MADE")
    original = tampered[pick_index]
    other_uid = next(
        uid for uid in original.payload["offered_uids"] if uid != original.payload["picked_uid"]
    )
    tampered_event = original.model_copy(
        update={"payload": {**original.payload, "picked_uid": other_uid}}
    )
    tampered[pick_index] = tampered_event

    assert events_match(golden_events, golden_events) is True
    assert events_match(golden_events, tampered) is False

    mismatch = first_mismatch(golden_events, tampered)
    assert mismatch is not None
    index, a, b = mismatch
    assert index == pick_index
    assert a is not None and b is not None
    assert a["payload"]["picked_uid"] != b["payload"]["picked_uid"]


def test_events_match_detects_length_mismatch() -> None:
    golden_events = read_events(GOLDEN_PATH)
    assert events_match(golden_events, golden_events[:-1]) is False


async def test_replay_raises_on_empty_event_log(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    with pytest.raises(ReplayError, match="empty"):
        await replay([], fixture_cards, fixture_pack_config)


async def test_replay_raises_when_seed_or_pod_size_missing(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    golden_events = read_events(GOLDEN_PATH)
    without_seed_or_pod = [e for e in golden_events if e.type not in ("SEED_SET", "POD_SEATED")]
    with pytest.raises(ReplayError, match="SEED_SET/POD_SEATED"):
        await replay(without_seed_or_pod, fixture_cards, fixture_pack_config)


def test_recorded_pick_source_replays_in_order_then_declines() -> None:
    golden_events = read_events(GOLDEN_PATH)
    source: RecordedPickSource = recorded_pick_source_from_events(golden_events)
    seat0_recorded = [
        e.payload["picked_uid"]
        for e in sorted(
            (e for e in golden_events if e.type == "PICK_MADE" and e.seat == 0),
            key=lambda e: (e.round, e.pick_number),
        )
    ]
    assert [uid for uid, _was_auto, _reason in source.picks_by_seat[0]] == seat0_recorded
    assert all(not was_auto for _uid, was_auto, _reason in source.picks_by_seat[0])


async def test_recorded_pick_source_returns_none_once_exhausted() -> None:
    source = RecordedPickSource(picks_by_seat={0: [("only-one-uid", False, None)]})
    assert await source.get_pick(0, [], None) == "only-one-uid"
    assert await source.get_pick(0, [], None) is None


async def test_recorded_pick_source_returns_none_for_unknown_seat() -> None:
    source = RecordedPickSource(picks_by_seat={})
    assert await source.get_pick(5, [], None) is None


async def test_recorded_pick_source_replays_no_response_auto_pick_as_none() -> None:
    source = RecordedPickSource(picks_by_seat={0: [("some-uid", True, "no_response")]})
    assert await source.get_pick(0, [], None) is None


async def test_recorded_pick_source_replays_invalid_decision_as_sentinel() -> None:
    source = RecordedPickSource(picks_by_seat={0: [("some-uid", True, "invalid_decision")]})
    result = await source.get_pick(0, [], None)
    assert result is not None
    assert result != "some-uid"
