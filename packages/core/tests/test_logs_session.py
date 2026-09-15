"""Tests for the session.json writer (WP-11, plan section 7)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fabdraft_core.contracts import Card, DraftEvent, PackConfig, SetSnapshot
from fabdraft_core.draft.engine import run_draft
from fabdraft_core.logs.session import build_session_summary, write_session_json

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_SET_PATH = REPO_ROOT / "data" / "fixtures" / "fixture_set.json"
FIXTURE_PACK_CONFIG_PATH = REPO_ROOT / "data" / "config" / "fixture.pack_config.json"


class AlwaysTimesOutForSeatZero:
    async def get_pick(self, seat: int, pack: list[Card], deadline_ms: int | None) -> str | None:
        if seat == 0:
            return None
        return pack[0].uid


@pytest.fixture(scope="module")
def fixture_cards() -> list[Card]:
    return SetSnapshot.model_validate(json.loads(FIXTURE_SET_PATH.read_text())).cards


@pytest.fixture(scope="module")
def fixture_pack_config() -> PackConfig:
    return PackConfig.model_validate(json.loads(FIXTURE_PACK_CONFIG_PATH.read_text()))


@pytest.fixture(scope="module")
def real_events(fixture_cards: list[Card], fixture_pack_config: PackConfig) -> list[DraftEvent]:
    async def _run() -> list[DraftEvent]:
        _, store = await run_draft(
            session_id="wp11-session-test",
            seed="wp11-session-seed",
            cards=fixture_cards,
            pack_config=fixture_pack_config,
            pick_source=AlwaysTimesOutForSeatZero(),
        )
        return store.events

    return asyncio.run(_run())


def test_summary_has_real_seed_pod_size_and_counts(real_events: list[DraftEvent]) -> None:
    summary = build_session_summary(real_events, seat_labels={0: "human", 1: "heuristic"})
    assert summary["session_id"] == "wp11-session-test"
    assert summary["seed"] == "wp11-session-seed"
    assert summary["pod_size"] == 8
    assert summary["total_picks"] == 336
    assert summary["timeout_counts"] == {0: 42}
    assert summary["seat_agents"] == {0: "human", 1: "heuristic"}
    assert summary["started_at"] is not None
    assert summary["ended_at"] is not None


def test_summary_degrades_gracefully_with_no_deck_build_events(
    real_events: list[DraftEvent],
) -> None:
    summary = build_session_summary(real_events)
    assert summary["per_seat_hero"] == {}
    assert summary["deck_validity"] == {}
    assert summary["llm_cost_usage"] == {}


def test_summary_populates_hero_and_validity_when_present() -> None:
    events = [
        DraftEvent.model_validate(
            {
                "event_id": 0,
                "session_id": "s",
                "ts_sim_ms": 0,
                "ts_wall": "2026-09-14T00:00:00Z",
                "type": "SEED_SET",
                "payload": {"seed": "x"},
            }
        ),
        DraftEvent.model_validate(
            {
                "event_id": 1,
                "session_id": "s",
                "ts_sim_ms": 0,
                "ts_wall": "2026-09-14T00:00:01Z",
                "type": "HERO_SELECTED",
                "seat": 3,
                "payload": {"hero_uid": "some-hero-none"},
            }
        ),
        DraftEvent.model_validate(
            {
                "event_id": 2,
                "session_id": "s",
                "ts_sim_ms": 0,
                "ts_wall": "2026-09-14T00:00:02Z",
                "type": "VALIDATION_RESULT",
                "seat": 3,
                "payload": {"valid": True},
            }
        ),
    ]
    summary = build_session_summary(events)
    assert summary["per_seat_hero"] == {3: "some-hero-none"}
    assert summary["deck_validity"] == {3: True}


def test_empty_event_log_summary_has_sane_defaults() -> None:
    summary = build_session_summary([])
    assert summary["session_id"] is None
    assert summary["total_picks"] == 0
    assert summary["timeout_counts"] == {}


def test_write_session_json_round_trips(real_events: list[DraftEvent], tmp_path: Path) -> None:
    summary = build_session_summary(real_events)
    path = tmp_path / "runs" / "session-x" / "session.json"
    write_session_json(path, summary)
    written = json.loads(path.read_text())
    assert written["session_id"] == "wp11-session-test"
    assert written["total_picks"] == 336
