"""Tests for the draft_log.md renderer (WP-11, plan section 7).

The golden-file-style test runs a real draft (FIXTURE set) through
fabdraft_core.draft.engine.run_draft and renders its actual event log -
proving the renderer works against real WP-07 output, not just hand-built
events.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fabdraft_core.contracts import Card, DraftEvent, PackConfig, SetSnapshot
from fabdraft_core.draft.engine import run_draft
from fabdraft_core.logs.markdown import render_draft_log, write_draft_log

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_SET_PATH = REPO_ROOT / "data" / "fixtures" / "fixture_set.json"
FIXTURE_PACK_CONFIG_PATH = REPO_ROOT / "data" / "config" / "fixture.pack_config.json"


class FirstAvailablePickSource:
    async def get_pick(self, seat: int, pack: list[Card], deadline_ms: int | None) -> str | None:
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
            session_id="wp11-golden",
            seed="wp11-golden-seed",
            cards=fixture_cards,
            pack_config=fixture_pack_config,
            pick_source=FirstAvailablePickSource(),
        )
        return store.events

    return asyncio.run(_run())


def test_golden_draft_log_contains_every_documented_section(
    real_events: list[DraftEvent], fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    markdown = render_draft_log(
        real_events,
        fixture_cards,
        seat_labels={s: "heuristic" for s in range(8)},
        casual_mode=False,
        data_integrity="complete",
        pack_config=fixture_pack_config,
    )

    assert markdown.startswith("# Draft Log")
    assert "**Seed:** wp11-golden-seed" in markdown
    assert "**Pod size:** 8" in markdown
    assert "**Seat configuration:** seat 0: heuristic" in markdown
    # 3 rounds, 14 picks each - spot check structure is present.
    for round_number in (1, 2, 3):
        assert f"## Round {round_number}" in markdown
    assert "#### Pick 1 (pack size 14)" in markdown
    assert "#### Pick 14 (pack size 1)" in markdown
    assert "picked **" in markdown
    assert "Offered:" in markdown
    assert "**Review:** window 60s, skipped=True" in markdown
    assert "## Pool finalized: 336 total cards drafted" in markdown
    # No deck-build orchestrator exists yet - must say so, not error/omit silently.
    assert "## Deck build" in markdown
    assert "_Pending:" in markdown


def test_golden_draft_log_resolves_real_card_names_and_stats(
    real_events: list[DraftEvent], fixture_cards: list[Card]
) -> None:
    markdown = render_draft_log(real_events, fixture_cards)
    # every card is FIXTURE-named; spot check at least one full card summary
    # (name, pitch or rarity, and a stat) shows up verbatim somewhere.
    sample = fixture_cards[0]
    assert sample.name in markdown
    assert sample.rarity in markdown


def test_timeout_and_reason_are_rendered_when_present(fixture_cards: list[Card]) -> None:
    event = DraftEvent.model_validate(
        {
            "event_id": 0,
            "session_id": "s",
            "ts_sim_ms": 0,
            "ts_wall": "2026-09-14T00:00:00Z",
            "type": "PICK_AUTO",
            "round": 1,
            "pick_number": 1,
            "seat": 0,
            "payload": {
                "pack_id": "r1p0",
                "pack_size_before": 1,
                "offered_uids": [fixture_cards[0].uid],
                "picked_uid": fixture_cards[0].uid,
                "timed_out": True,
                "reason": "no_response",
            },
        }
    )
    markdown = render_draft_log([event], fixture_cards)
    assert "TIMED OUT, no_response" in markdown


def test_model_reasoning_and_alternatives_are_rendered_when_present(
    fixture_cards: list[Card],
) -> None:
    """plan section 7: 'for model seats the recorded reasoning and
    alternatives.' No agent exists yet (WP-14), so this payload shape is
    hypothetical - but the renderer must handle it once one shows up.
    """
    event = DraftEvent.model_validate(
        {
            "event_id": 0,
            "session_id": "s",
            "ts_sim_ms": 0,
            "ts_wall": "2026-09-14T00:00:00Z",
            "type": "PICK_MADE",
            "round": 1,
            "pick_number": 1,
            "seat": 0,
            "payload": {
                "pack_id": "r1p0",
                "pack_size_before": 1,
                "offered_uids": [fixture_cards[0].uid],
                "picked_uid": fixture_cards[0].uid,
                "timed_out": False,
                "agent": {"kind": "llm", "model": "test-model"},
                "decision": {
                    "reasoning": "best card in the pack",
                    "ranked_alternatives": [{"uid": "x", "score": 0.5}],
                },
            },
        }
    )
    markdown = render_draft_log([event], fixture_cards)
    assert "Agent: {'kind': 'llm', 'model': 'test-model'}" in markdown
    assert "Reasoning: best card in the pack" in markdown
    assert "Alternatives:" in markdown


def test_deck_build_events_are_rendered_when_present() -> None:
    event = DraftEvent.model_validate(
        {
            "event_id": 0,
            "session_id": "s",
            "ts_sim_ms": 0,
            "ts_wall": "2026-09-14T00:00:00Z",
            "type": "HERO_SELECTED",
            "round": None,
            "pick_number": None,
            "seat": 2,
            "payload": {"hero_uid": "some-hero-none"},
        }
    )
    markdown = render_draft_log([event], [])
    assert "## Deck build" in markdown
    assert "_Pending:" not in markdown
    assert "HERO_SELECTED" in markdown
    assert "some-hero-none" in markdown


def test_write_draft_log_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "runs" / "session-x" / "draft_log.md"
    write_draft_log(path, "# hello\n")
    assert path.read_text() == "# hello\n"


def test_empty_event_log_renders_without_crashing() -> None:
    markdown = render_draft_log([], [])
    assert markdown.startswith("# Draft Log")
    assert "(empty log)" in markdown
