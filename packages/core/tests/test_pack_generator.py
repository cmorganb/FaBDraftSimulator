"""Tests for the pack generator (WP-05, plan section 6.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fabdraft_core.contracts import Card, PackConfig, SetSnapshot
from fabdraft_core.errors import PackGenerationError
from fabdraft_core.packs.generator import generate_pack, index_by_rarity
from fabdraft_core.rng import rng_for

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_SET_PATH = REPO_ROOT / "data" / "fixtures" / "fixture_set.json"
FIXTURE_PACK_CONFIG_PATH = REPO_ROOT / "data" / "config" / "fixture.pack_config.json"
IAR_PACK_CONFIG_PATH = REPO_ROOT / "data" / "config" / "iar.pack_config.json"


@pytest.fixture(scope="module")
def fixture_cards() -> list[Card]:
    snapshot = SetSnapshot.model_validate(json.loads(FIXTURE_SET_PATH.read_text()))
    return snapshot.cards


@pytest.fixture(scope="module")
def fixture_pack_config() -> PackConfig:
    return PackConfig.model_validate(json.loads(FIXTURE_PACK_CONFIG_PATH.read_text()))


def test_iar_pack_config_is_schema_valid_and_matches_s9() -> None:
    config = PackConfig.model_validate(json.loads(IAR_PACK_CONFIG_PATH.read_text()))
    assert config.pack_size == 16
    draftable_count = sum(s.count for s in config.slots if s.draftable)
    assert draftable_count == 14  # plan S9


def test_index_by_rarity_excludes_arena_cards(fixture_cards: list[Card]) -> None:
    index = index_by_rarity(fixture_cards)
    all_indexed = [c for cards in index.values() for c in cards]
    assert all(c.is_deck_card for c in all_indexed)
    assert all(not c.is_arena_card for c in all_indexed)


def test_generate_pack_has_correct_size_and_draftable_count(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    rng = rng_for("seed-1", "pack", 1, 0)
    pack = generate_pack(fixture_cards, fixture_pack_config, rng)
    assert len(pack.cards) == 16
    assert len(pack.draftable_cards) == 14


def test_generate_pack_preserves_physical_slot_order(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    rng = rng_for("seed-1", "pack", 1, 0)
    pack = generate_pack(fixture_cards, fixture_pack_config, rng)
    slot_ids = [c.slot_id for c in pack.cards]
    # 11 commons, then rare, rare_or_majestic, rainbow_foil, basic, chase -
    # each slot's cards are contiguous and in declared order.
    assert slot_ids == (
        ["common"] * 11 + ["rare", "rare_or_majestic", "rainbow_foil", "basic", "chase"]
    )
    assert [c.draftable for c in pack.cards[:14]] == [True] * 14
    assert [c.draftable for c in pack.cards[14:]] == [False] * 2


def test_no_duplicate_uids_within_a_pack(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    for i in range(200):
        rng = rng_for("seed-1", "pack", 1, i)
        pack = generate_pack(fixture_cards, fixture_pack_config, rng)
        uids = [c.card.uid for c in pack.cards]
        assert len(set(uids)) == len(uids), f"pack {i} had a duplicate uid"


def test_expansion_slot_majestics_never_appear_in_a_draftable_slot(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    for i in range(300):
        rng = rng_for("seed-1", "pack", 1, i)
        pack = generate_pack(fixture_cards, fixture_pack_config, rng)
        for packed in pack.draftable_cards:
            if packed.card.rarity == "M":
                assert not packed.card.is_expansion_slot, (
                    f"pack {i}, slot {packed.slot_id}: expansion majestic in a draftable slot"
                )


def test_no_hero_weapon_or_equipment_ever_appears_in_a_pack(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    for i in range(50):
        rng = rng_for("seed-1", "pack", 1, i)
        pack = generate_pack(fixture_cards, fixture_pack_config, rng)
        assert all(not c.card.is_arena_card for c in pack.cards)


def test_same_seed_gives_identical_packs(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    rng_a = rng_for("seed-1", "pack", 2, 3)
    rng_b = rng_for("seed-1", "pack", 2, 3)
    pack_a = generate_pack(fixture_cards, fixture_pack_config, rng_a)
    pack_b = generate_pack(fixture_cards, fixture_pack_config, rng_b)
    assert [c.card.uid for c in pack_a.cards] == [c.card.uid for c in pack_b.cards]


def test_different_pack_index_gives_a_different_pack(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    rng_a = rng_for("seed-1", "pack", 1, 0)
    rng_b = rng_for("seed-1", "pack", 1, 1)
    pack_a = generate_pack(fixture_cards, fixture_pack_config, rng_a)
    pack_b = generate_pack(fixture_cards, fixture_pack_config, rng_b)
    assert [c.card.uid for c in pack_a.cards] != [c.card.uid for c in pack_b.cards]


def test_statistical_distribution_matches_configured_weights_over_10k_packs(
    fixture_cards: list[Card], fixture_pack_config: PackConfig
) -> None:
    """plan WP-05 acceptance: '10k-pack statistical test within tolerance of
    configured weights'. Uses the rare_or_majestic slot (R 0.5 / M-core 0.5).
    """
    rare_count = 0
    majestic_count = 0
    n = 10_000
    for i in range(n):
        rng = rng_for("seed-stat", "pack", 1, i)
        pack = generate_pack(fixture_cards, fixture_pack_config, rng)
        picked = next(c for c in pack.cards if c.slot_id == "rare_or_majestic")
        if picked.card.rarity == "R":
            rare_count += 1
        else:
            assert picked.card.rarity == "M"
            majestic_count += 1

    assert rare_count + majestic_count == n
    rare_ratio = rare_count / n
    assert 0.45 < rare_ratio < 0.55  # configured weight is 0.5, +/- 5pp tolerance


def _majestic_card(uid: str, *, is_expansion_slot: bool) -> Card:
    return Card.model_validate(
        {
            "uid": uid,
            "set_code": "TINY",
            "card_number": uid.upper(),
            "name": uid,
            "pitch": 1,
            "rarity": "M",
            "types": ["Action"],
            "classes": [],
            "talents": [],
            "subtypes": [],
            "cost": 1,
            "power": 1,
            "defense": 1,
            "life": None,
            "intellect": None,
            "keywords": [],
            "functional_text": "",
            "specialization": None,
            "is_deck_card": True,
            "is_arena_card": False,
            "equipment_slot": None,
            "hands": None,
            "image_url": None,
            "double_faced_with": None,
            "draftable": not is_expansion_slot,
            "is_expansion_slot": is_expansion_slot,
            "data_complete": True,
        }
    )


def test_an_explicit_expansion_majestic_subset_slot_only_draws_expansion_majestics() -> None:
    cards = [
        _majestic_card("core-a", is_expansion_slot=False),
        _majestic_card("expansion-a", is_expansion_slot=True),
    ]
    config = PackConfig.model_validate(
        {
            "set_code": "TINY",
            "pack_size": 1,
            "slots": [
                {
                    "id": "expansion_only",
                    "count": 1,
                    "rarities": {"M": 1.0},
                    "majestic_subset": "expansion",
                    "draftable": False,
                }
            ],
            "no_duplicate_uids_within_pack": True,
            "cold_foil_rate_per_pack": 0.0,
        }
    )
    for i in range(20):
        rng = rng_for("seed-1", "pack", 1, i)
        pack = generate_pack(cards, config, rng)
        assert pack.cards[0].card.uid == "expansion-a"


def test_pack_generation_error_on_pool_exhaustion() -> None:
    tiny_cards = [
        Card.model_validate(
            {
                "uid": f"tiny-{i}",
                "set_code": "TINY",
                "card_number": f"TINY00{i}",
                "name": f"Tiny {i}",
                "pitch": 1,
                "rarity": "C",
                "types": ["Action"],
                "classes": [],
                "talents": [],
                "subtypes": [],
                "cost": 1,
                "power": 1,
                "defense": 1,
                "life": None,
                "intellect": None,
                "keywords": [],
                "functional_text": "",
                "specialization": None,
                "is_deck_card": True,
                "is_arena_card": False,
                "equipment_slot": None,
                "hands": None,
                "image_url": None,
                "double_faced_with": None,
                "draftable": True,
                "is_expansion_slot": False,
                "data_complete": True,
            }
        )
        for i in range(2)
    ]
    config = PackConfig.model_validate(
        {
            "set_code": "TINY",
            "pack_size": 3,
            "slots": [{"id": "common", "count": 3, "rarities": {"C": 1.0}, "draftable": True}],
            "no_duplicate_uids_within_pack": True,
            "cold_foil_rate_per_pack": 0.0,
        }
    )
    rng = rng_for("seed-1", "pack", 1, 0)
    with pytest.raises(PackGenerationError, match="no candidates left"):
        generate_pack(tiny_cards, config, rng)


def test_pack_generation_error_on_pack_size_mismatch(fixture_cards: list[Card]) -> None:
    bad_config = PackConfig.model_validate(
        {
            "set_code": "FIXTURE",
            "pack_size": 99,  # doesn't match the sum of slot counts below
            "slots": [{"id": "common", "count": 1, "rarities": {"C": 1.0}, "draftable": True}],
            "no_duplicate_uids_within_pack": True,
            "cold_foil_rate_per_pack": 0.0,
        }
    )
    rng = rng_for("seed-1", "pack", 1, 0)
    with pytest.raises(PackGenerationError, match="pack_size"):
        generate_pack(fixture_cards, bad_config, rng)


def test_pack_generation_error_on_unrecognized_rarity_key(fixture_cards: list[Card]) -> None:
    bad_config = PackConfig.model_validate(
        {
            "set_code": "FIXTURE",
            "pack_size": 1,
            "slots": [
                {"id": "mystery", "count": 1, "rarities": {"NOT_A_RARITY": 1.0}, "draftable": True}
            ],
            "no_duplicate_uids_within_pack": True,
            "cold_foil_rate_per_pack": 0.0,
        }
    )
    rng = rng_for("seed-1", "pack", 1, 0)
    with pytest.raises(PackGenerationError, match="unrecognized rarity key"):
        generate_pack(fixture_cards, bad_config, rng)
