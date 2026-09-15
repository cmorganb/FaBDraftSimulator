"""Tests for deck build + validation (WP-09, plan section 6.3).

Every violation code in contracts/decklist.schema.json's Violation.code
enum is reached at least once, plus a fully-valid case and the hero's own
basic-gear auto-availability (plan S10).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fabdraft_core.cards.legality import FormatRules
from fabdraft_core.contracts import Card
from fabdraft_core.deck.builder import DEFAULT_DECK_SIZE, legal_pool, validate_deck

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_FORMAT_PATH = REPO_ROOT / "data" / "config" / "fixture.format.json"


def _card(
    uid: str,
    *,
    rarity: str = "C",
    classes: list[str] | None = None,
    talents: list[str] | None = None,
    object_type: str = "deck",
    name: str | None = None,
    specialization: str | None = None,
    equipment_slot: str | None = None,
    hands: int | None = None,
    subtypes: list[str] | None = None,
) -> Card:
    return Card(
        uid=uid,
        set_code="FIXTURE",
        card_number=uid.upper(),
        name=name or uid,
        pitch=1 if object_type == "deck" else None,
        rarity=rarity,  # type: ignore[arg-type]
        types=["Action"] if object_type == "deck" else ["Equipment"],
        classes=classes or [],
        talents=talents or [],
        subtypes=subtypes or [],
        cost=1,
        power=2,
        defense=2,
        life=None,
        intellect=None,
        keywords=[],
        functional_text="",
        specialization=specialization,
        object_type=object_type,  # type: ignore[arg-type]
        is_deck_card=object_type == "deck",
        is_arena_card=object_type == "arena",
        equipment_slot=equipment_slot,  # type: ignore[arg-type]
        hands=hands,  # type: ignore[arg-type]
        image_url=None,
        double_faced_with=None,
        draftable=True,
        is_expansion_slot=False,
        data_complete=True,
    )


def _hero(name: str, *, classes: list[str], talents: list[str], young: bool = True) -> Card:
    return _card(
        uid=f"hero-{name.lower().replace(' ', '-').replace(',', '')}",
        rarity="B",
        classes=classes,
        talents=talents,
        object_type="hero",
        name=name,
        subtypes=["Young"] if young else [],
    )


def _full_legal_deck(hero: Card) -> list[Card]:
    return [
        _card(f"deck-card-{i}", classes=hero.classes, talents=hero.talents)
        for i in range(DEFAULT_DECK_SIZE)
    ]


def test_legal_pool_includes_drafted_and_all_basics_without_duplicates() -> None:
    drafted = [_card("common-1"), _card("basic-drafted", rarity="B")]
    all_set_cards = [
        _card("common-1"),
        _card("common-2"),
        _card("basic-drafted", rarity="B"),
        _card("basic-not-drafted", rarity="B"),
    ]
    pool = legal_pool(drafted, all_set_cards)
    pool_uids = [c.uid for c in pool]
    assert pool_uids.count("basic-drafted") == 1
    assert "basic-not-drafted" in pool_uids
    assert "common-2" not in pool_uids  # never drafted, not Basic - correctly excluded


def test_fully_valid_deck_has_no_violations() -> None:
    hero = _hero("Fixture Hero", classes=["Brute"], talents=["Shadow"])
    deck_cards = _full_legal_deck(hero)
    weapon = _card(
        "weapon-1",
        rarity="B",
        object_type="arena",
        classes=hero.classes,
        talents=hero.talents,
        hands=2,
    )
    arm = _card(
        "arm-1",
        rarity="B",
        object_type="arena",
        classes=hero.classes,
        talents=hero.talents,
        equipment_slot="arms",
    )
    pool = [hero, weapon, arm, *deck_cards]
    result = validate_deck(pool=pool, hero=hero, arena_cards=[weapon, arm], deck_cards=deck_cards)
    assert result.valid is True
    assert result.violations == ()


def test_no_hero_violation() -> None:
    result = validate_deck(pool=[], hero=None, arena_cards=[], deck_cards=[])
    codes = [v.code for v in result.violations]
    assert "NO_HERO" in codes


def test_hero_not_young_violation() -> None:
    hero = _hero("Adult Hero", classes=["Brute"], talents=["Shadow"], young=False)
    result = validate_deck(pool=[hero], hero=hero, arena_cards=[], deck_cards=[])
    codes = [v.code for v in result.violations]
    assert "HERO_NOT_YOUNG" in codes


def test_hero_wrong_object_type_raises() -> None:
    not_a_hero = _card("x", object_type="deck")
    with pytest.raises(ValueError, match="object_type='hero'"):
        validate_deck(pool=[], hero=not_a_hero, arena_cards=[], deck_cards=[])


def test_deck_size_violation() -> None:
    hero = _hero("Fixture Hero", classes=["Brute"], talents=["Shadow"])
    short_deck = [_card(f"deck-card-{i}") for i in range(29)]
    result = validate_deck(
        pool=[hero, *short_deck], hero=hero, arena_cards=[], deck_cards=short_deck
    )
    codes = [v.code for v in result.violations]
    assert "DECK_SIZE" in codes


def test_not_in_pool_violation() -> None:
    hero = _hero("Fixture Hero", classes=["Brute"], talents=["Shadow"])
    deck_cards = _full_legal_deck(hero)
    outsider = _card("never-drafted")
    deck_cards[0] = outsider
    result = validate_deck(
        pool=[hero, *deck_cards[1:]], hero=hero, arena_cards=[], deck_cards=deck_cards
    )
    codes = [v.code for v in result.violations]
    assert "NOT_IN_POOL" in codes


def test_illegal_card_violation() -> None:
    hero = _hero("Fixture Hero", classes=["Brute"], talents=["Shadow"])
    deck_cards = _full_legal_deck(hero)
    mismatched = _card("wrong-class", classes=["Ninja"], talents=[])
    deck_cards[0] = mismatched
    result = validate_deck(
        pool=[hero, mismatched, *deck_cards[1:]],
        hero=hero,
        arena_cards=[],
        deck_cards=deck_cards,
    )
    codes = [v.code for v in result.violations]
    assert "ILLEGAL_CARD" in codes


def test_arena_card_in_deck_violation() -> None:
    hero = _hero("Fixture Hero", classes=["Brute"], talents=["Shadow"])
    deck_cards = _full_legal_deck(hero)
    weapon = _card("a-weapon", rarity="B", object_type="arena", classes=hero.classes, hands=1)
    deck_cards[0] = weapon
    result = validate_deck(
        pool=[hero, weapon, *deck_cards[1:]], hero=hero, arena_cards=[], deck_cards=deck_cards
    )
    codes = [v.code for v in result.violations]
    assert "ARENA_CARD_IN_DECK" in codes


def test_equip_slot_conflict_violation() -> None:
    hero = _hero("Fixture Hero", classes=["Brute"], talents=["Shadow"])
    head_1 = _card("head-1", rarity="B", object_type="arena", equipment_slot="head")
    head_2 = _card("head-2", rarity="B", object_type="arena", equipment_slot="head")
    deck_cards = _full_legal_deck(hero)
    result = validate_deck(
        pool=[hero, head_1, head_2, *deck_cards],
        hero=hero,
        arena_cards=[head_1, head_2],
        deck_cards=deck_cards,
    )
    codes = [v.code for v in result.violations]
    assert "EQUIP_SLOT_CONFLICT" in codes


def test_weapon_hands_violation() -> None:
    hero = _hero("Fixture Hero", classes=["Brute"], talents=["Shadow"])
    weapon_a = _card("weapon-a", rarity="B", object_type="arena", hands=2)
    weapon_b = _card("weapon-b", rarity="B", object_type="arena", hands=1)
    deck_cards = _full_legal_deck(hero)
    result = validate_deck(
        pool=[hero, weapon_a, weapon_b, *deck_cards],
        hero=hero,
        arena_cards=[weapon_a, weapon_b],
        deck_cards=deck_cards,
    )
    codes = [v.code for v in result.violations]
    assert "WEAPON_HANDS" in codes


def test_two_one_handed_weapons_do_not_violate_weapon_hands() -> None:
    hero = _hero("Fixture Hero", classes=["Brute"], talents=["Shadow"])
    weapon_a = _card("weapon-a", rarity="B", object_type="arena", hands=1)
    weapon_b = _card("weapon-b", rarity="B", object_type="arena", hands=1)
    deck_cards = _full_legal_deck(hero)
    result = validate_deck(
        pool=[hero, weapon_a, weapon_b, *deck_cards],
        hero=hero,
        arena_cards=[weapon_a, weapon_b],
        deck_cards=deck_cards,
    )
    codes = [v.code for v in result.violations]
    assert "WEAPON_HANDS" not in codes


def test_format_restriction_violation() -> None:
    hero = _hero("Fixture Hero", classes=["Brute"], talents=["Shadow"])
    deck_cards = _full_legal_deck(hero)
    banned = deck_cards[0]
    rules = FormatRules(banned_in_limited=frozenset({banned.uid}))
    result = validate_deck(
        pool=[hero, *deck_cards],
        hero=hero,
        arena_cards=[],
        deck_cards=deck_cards,
        format_rules=rules,
    )
    codes = [v.code for v in result.violations]
    assert "FORMAT_RESTRICTION" in codes


def test_format_restriction_fires_even_without_a_hero() -> None:
    """FORMAT_RESTRICTION is a format-wide fact, independent of hero
    selection - unlike ILLEGAL_CARD, which needs a hero to check against.
    """
    banned = _card("banned-card")
    rules = FormatRules(banned_in_limited=frozenset({banned.uid}))
    result = validate_deck(
        pool=[banned], hero=None, arena_cards=[banned], deck_cards=[], format_rules=rules
    )
    codes = [v.code for v in result.violations]
    assert "FORMAT_RESTRICTION" in codes
    assert "ILLEGAL_CARD" not in codes


def test_heros_own_basic_gear_is_auto_available_and_legal() -> None:
    """plan S10: a young hero's own basic weapon and arm equipment don't
    need to be drafted - they come from the general Basic-rarity-unlimited
    rule (plan L1), with no special-casing required.
    """
    format_config = json.loads(FIXTURE_FORMAT_PATH.read_text())
    hero_info = format_config["heroes"][0]
    hero = _hero(
        hero_info["name"],
        classes=hero_info["classes"],
        talents=hero_info["talents"],
    )
    weapon = _card(
        hero_info["basic_weapon_uids"][0],
        rarity="B",
        object_type="arena",
        classes=hero.classes,
        talents=hero.talents,
        hands=1,
    )
    arm = _card(
        hero_info["basic_equipment_uids"][0],
        rarity="B",
        object_type="arena",
        classes=hero.classes,
        talents=hero.talents,
        equipment_slot="arms",
    )
    # Never drafted (not in `drafted_cards`) - only available via the
    # Basic-rarity-unlimited rule.
    all_set_cards = [hero, weapon, arm]
    pool = legal_pool(drafted_cards=[], all_set_cards=all_set_cards)
    assert weapon.uid in {c.uid for c in pool}
    assert arm.uid in {c.uid for c in pool}

    deck_cards = _full_legal_deck(hero)
    result = validate_deck(
        pool=[*pool, *deck_cards], hero=hero, arena_cards=[weapon, arm], deck_cards=deck_cards
    )
    assert result.valid is True


def test_a_different_heros_basic_gear_is_available_but_illegal() -> None:
    """Auto-availability (plan L1) is unconditional, but legality
    (class/talent subset, WP-06) still gates *use* - so a Necromancer's
    weapon is in the pool but illegal for a Brute hero.
    """
    brute = _hero("Fixture Brute", classes=["Brute"], talents=["Shadow"])
    necromancer_weapon = _card(
        "necromancer-weapon", rarity="B", object_type="arena", classes=["Necromancer"], hands=1
    )
    pool = legal_pool(drafted_cards=[], all_set_cards=[brute, necromancer_weapon])
    assert necromancer_weapon.uid in {c.uid for c in pool}

    deck_cards = _full_legal_deck(brute)
    result = validate_deck(
        pool=[*pool, *deck_cards],
        hero=brute,
        arena_cards=[necromancer_weapon],
        deck_cards=deck_cards,
    )
    codes = [v.code for v in result.violations]
    assert "ILLEGAL_CARD" in codes
