"""Unit tests for the ingestion mapping logic (WP-01). Fixtures under
scripts/tests/fixtures/ are entirely fictional (invented names/text shaped
like the real upstream schema) - never real Legend Story Studios card text,
per plan section 0 item 3 and the "zero hand-typed card text" acceptance
criterion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fabdraft_core.errors import DataIncompleteError
from scripts.ingest_set import (
    build_snapshot,
    cards_for_set,
    classify_types,
    derive_equipment,
    derive_specialization,
    make_uid,
    map_card,
    parse_int,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_cards() -> list[dict]:
    return json.loads((FIXTURES_DIR / "mock_upstream_cards.json").read_text())


def test_parse_int_handles_blank_and_variable_values() -> None:
    assert parse_int("3") == 3
    assert parse_int("") is None
    assert parse_int(None) is None
    assert parse_int("X") is None
    assert parse_int("*") is None


def test_make_uid_is_name_plus_pitch_and_stable_across_printings() -> None:
    assert make_uid("Fixture Swift Strike", 1) == "fixture-swift-strike-red"
    assert make_uid("Fixture Rustblade", None) == "fixture-rustblade-none"


def test_classify_types_splits_class_talent_and_subtype() -> None:
    classes, talents, subtypes, fully = classify_types(["Runeblade", "Shadow", "Action", "Attack"])
    assert classes == ["Runeblade"]
    assert talents == ["Shadow"]
    assert subtypes == []
    assert fully is True


def test_classify_types_flags_unknown_token_as_incomplete() -> None:
    classes, talents, subtypes, fully = classify_types(["SomeUnknownFutureType"])
    assert classes == []
    assert talents == []
    assert subtypes == ["SomeUnknownFutureType"]
    assert fully is False


def test_derive_specialization_extracts_hero_name() -> None:
    assert (
        derive_specialization("Blood Debt\nSpecialization: Fixture Hero One.") == "Fixture Hero One"
    )
    assert derive_specialization("No specialization text here.") is None


def test_derive_equipment_detects_weapon_hands() -> None:
    assert derive_equipment(["Weapon", "One Hand"]) == (None, 1)
    assert derive_equipment(["Head"]) == ("head", None)
    assert derive_equipment(["Action"]) == (None, None)


def test_map_card_generic_common(mock_cards: list[dict]) -> None:
    raw = mock_cards[0]
    card = map_card(raw, raw["printings"][0], "MOCK")
    assert card.uid == "fixture-swift-strike-red"
    assert card.rarity == "C"
    assert card.classes == []
    assert card.talents == []
    assert card.pitch == 1
    assert card.is_arena_card is False
    assert card.data_complete is True


def test_map_card_class_talent_and_specialization(mock_cards: list[dict]) -> None:
    raw = mock_cards[1]
    card = map_card(raw, raw["printings"][0], "MOCK")
    assert card.classes == ["Runeblade"]
    assert card.talents == ["Shadow"]
    assert card.specialization == "Fixture Hero One"
    assert card.rarity == "M"
    assert "Blood Debt" in card.keywords


def test_map_card_weapon_is_arena_card_with_inferred_basic_rarity(mock_cards: list[dict]) -> None:
    raw = mock_cards[3]
    card = map_card(raw, raw["printings"][0], "MOCK")
    assert card.rarity == "B"
    assert card.is_arena_card is True
    assert card.is_deck_card is False
    assert card.hands == 1
    assert card.pitch is None


def test_map_card_unknown_type_marks_data_incomplete(mock_cards: list[dict]) -> None:
    raw = mock_cards[4]
    card = map_card(raw, raw["printings"][0], "MOCK")
    assert card.data_complete is False
    assert "SomeUnknownFutureType" in card.subtypes


def test_map_card_requires_a_rarity() -> None:
    raw = {"unique_id": "x", "name": "Fixture No Rarity", "pitch": "1", "types": []}
    with pytest.raises(DataIncompleteError):
        map_card(raw, {"id": "MOCK999", "set_id": "MOCK"}, "MOCK")


def test_map_card_rejects_unmapped_rarity_code() -> None:
    bad_cards = json.loads((FIXTURES_DIR / "mock_upstream_cards_bad_rarity.json").read_text())
    raw = bad_cards[0]
    with pytest.raises(DataIncompleteError, match="unmapped rarity"):
        map_card(raw, raw["printings"][0], "MOCK")


def test_cards_for_set_filters_by_set_id_and_excludes_other_sets(mock_cards: list[dict]) -> None:
    cards = cards_for_set(mock_cards, "MOCK")
    # mock_cards includes one card only printed for set_id "OTHER"
    assert len(cards) == 5
    assert all(c.set_code == "MOCK" for c in cards)
    assert "fixture-from-another-set-red" not in {c.uid for c in cards}


def test_build_snapshot_computes_counts_and_incomplete_list(mock_cards: list[dict]) -> None:
    expected_counts = {"total": 5, "F": 0, "V": 0, "L": 0, "M": 1, "R": 1, "C": 2, "B": 1}
    snapshot = build_snapshot(
        raw_cards=mock_cards,
        set_code="MOCK",
        set_name="Mock Fixture Set",
        release_date="2026-01-01",
        expected_counts=expected_counts,
        source_commit="deadbeef",
    )
    assert len(snapshot.cards) == 5
    assert snapshot.integrity.counts_match is True
    assert snapshot.integrity.incomplete_cards == ["fixture-mysterious-relic-none"]


def test_build_snapshot_raises_when_no_cards_match_set_code(mock_cards: list[dict]) -> None:
    with pytest.raises(DataIncompleteError, match="no cards found"):
        build_snapshot(
            raw_cards=mock_cards,
            set_code="NOPE",
            set_name="Nope",
            release_date="2026-01-01",
            expected_counts={"total": 0, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 0, "B": 0},
            source_commit="deadbeef",
        )
