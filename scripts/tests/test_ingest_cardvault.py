"""Unit tests for the Card Vault ingestion path (WP-05 amendment). Fixtures
under scripts/tests/fixtures/mock_cardvault_cards.json are entirely
fictional (invented names/text shaped like the real schema) - never real
Legend Story Studios card text, per plan section 0 item 3.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fabdraft_core.errors import DataIncompleteError
from scripts.ingest_cardvault import (
    build_snapshot,
    derive_cardvault_keywords,
    derive_cardvault_specialization,
    derive_equipment_from_subtypes,
    map_card,
    parse_numeric,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_payload() -> dict:
    return json.loads((FIXTURES_DIR / "mock_cardvault_cards.json").read_text())


@pytest.fixture
def mock_cards(mock_payload: dict) -> list[dict]:
    return mock_payload["cards"]


def test_parse_numeric_passes_through_ints_and_none_but_drops_strings() -> None:
    assert parse_numeric(3) == 3
    assert parse_numeric(None) is None
    assert parse_numeric("X") is None
    assert parse_numeric("*") is None


def test_derive_cardvault_specialization_matches_name_before_the_word() -> None:
    assert derive_cardvault_specialization("Viserai Specialization\nMore text.") == "Viserai"
    assert (
        derive_cardvault_specialization("Legendary Viserai Specialization (restriction)")
        == "Viserai"
    )
    assert derive_cardvault_specialization("No specialization here.") is None


def test_derive_cardvault_keywords_only_matches_known_allowlist() -> None:
    assert derive_cardvault_keywords("Blood Debt\nGo Again") == ["Blood Debt", "Go Again"]
    assert derive_cardvault_keywords("Some other totally different ability text") == []


def test_derive_equipment_from_subtypes() -> None:
    assert derive_equipment_from_subtypes(["(2H)", "Hammer"]) == (None, 2)
    assert derive_equipment_from_subtypes(["Head"]) == ("head", None)
    assert derive_equipment_from_subtypes([]) == (None, None)


def test_map_card_generic_common(mock_cards: list[dict]) -> None:
    card = map_card(mock_cards[0], "MOCK")
    assert card.uid == "fixture-common-1"
    assert card.rarity == "C"
    assert card.object_type == "deck"
    assert card.is_deck_card is True
    assert card.is_arena_card is False
    assert card.data_complete is True


def test_map_card_class_talent_and_specialization(mock_cards: list[dict]) -> None:
    card = map_card(mock_cards[1], "MOCK")
    assert card.classes == ["Runeblade"]
    assert card.talents == ["Shadow"]
    assert card.specialization == "Viserai"
    assert card.rarity == "M"


def test_map_card_normalizes_literal_generic_class_to_empty_list(mock_cards: list[dict]) -> None:
    card = map_card(mock_cards[2], "MOCK")
    assert card.classes == []
    assert card.object_type == "arena"
    assert card.equipment_slot == "head"
    assert card.rarity == "C"  # non-Basic arena card - pack-eligible


def test_map_card_expansion_slot_majestic_from_high_set_number(mock_cards: list[dict]) -> None:
    card = map_card(mock_cards[3], "MOCK")
    assert card.is_expansion_slot is True
    assert card.draftable is False


def test_map_card_hero_is_never_draftable_regardless_of_rarity(mock_cards: list[dict]) -> None:
    card = map_card(mock_cards[4], "MOCK")
    assert card.object_type == "hero"
    assert card.is_deck_card is False
    assert card.is_arena_card is False
    assert card.draftable is False


def test_map_card_token(mock_cards: list[dict]) -> None:
    card = map_card(mock_cards[5], "MOCK")
    assert card.object_type == "token"
    assert card.is_deck_card is False
    assert card.is_arena_card is False
    assert card.draftable is False


def test_map_card_weapon_hands_from_subtypes(mock_cards: list[dict]) -> None:
    card = map_card(mock_cards[6], "MOCK")
    assert card.object_type == "arena"
    assert card.hands == 2
    assert card.rarity == "B"
    assert card.draftable is False  # hero-tied Basic arena gear


def test_map_card_variable_cost_and_power_drop_to_none_and_mark_incomplete(
    mock_cards: list[dict],
) -> None:
    card = map_card(mock_cards[7], "MOCK")
    assert card.cost is None
    assert card.power is None
    assert card.data_complete is False


def test_map_card_rejects_unmapped_rarity(mock_cards: list[dict]) -> None:
    with pytest.raises(DataIncompleteError, match="unmapped rarity"):
        map_card(mock_cards[8], "MOCK")


def test_map_card_rejects_unmapped_object_type() -> None:
    raw = {
        "card_id": "x",
        "name": "X",
        "object_type": "not-a-real-type",
        "default_print_id": "X001",
        "rarity": "common",
        "faces": [{"name": "X", "classes": [], "talents": [], "types": [], "subtypes": []}],
        "printings": [{"print_id": "X001", "set_number": 1, "rarity": "common"}],
    }
    with pytest.raises(DataIncompleteError, match="unmapped object_type"):
        map_card(raw, "MOCK")


def test_map_card_requires_faces() -> None:
    raw = {
        "card_id": "x",
        "name": "X",
        "object_type": "deck-card",
        "default_print_id": "X001",
        "rarity": "common",
        "faces": [],
        "printings": [{"print_id": "X001", "set_number": 1, "rarity": "common"}],
    }
    with pytest.raises(DataIncompleteError, match="no faces"):
        map_card(raw, "MOCK")


def test_build_snapshot_maps_every_card_and_computes_counts(mock_payload: dict) -> None:
    expected_counts = {"total": 8, "F": 0, "V": 0, "L": 0, "M": 2, "R": 1, "C": 2, "B": 3}
    # drop the deliberately-bad-rarity card for this happy-path test
    payload = dict(mock_payload)
    payload["cards"] = [c for c in mock_payload["cards"] if c["card_id"] != "fixture-bad-rarity"]
    snapshot = build_snapshot(payload, "MOCK", expected_counts)
    assert len(snapshot.cards) == 8
    assert snapshot.integrity.counts_match is True
    assert "fixture-variable-5" in snapshot.integrity.incomplete_cards
