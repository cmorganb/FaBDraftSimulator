"""Tests for card-pool legality (WP-06, plan section 6.3).

The bulk of this is a data-driven pass over
tests/data/legality_cases.json - hand-checked cases for all three IAR
draft heroes, citing the exact CR/TRP rules being verified.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fabdraft_core.cards.legality import FormatRules, card_playable_by, moniker_of
from fabdraft_core.contracts import Card

CASES_PATH = Path(__file__).parent / "data" / "legality_cases.json"


def _card(
    uid: str,
    classes: list[str],
    talents: list[str],
    *,
    object_type: str = "deck",
    name: str | None = None,
    specialization: str | None = None,
) -> Card:
    return Card(
        uid=uid,
        set_code="FIXTURE",
        card_number=uid.upper(),
        name=name or uid,
        pitch=1,
        rarity="C",
        types=["Action"],
        classes=classes,
        talents=talents,
        subtypes=[],
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
        equipment_slot=None,
        hands=None,
        image_url=None,
        double_faced_with=None,
        draftable=True,
        is_expansion_slot=False,
        data_complete=True,
    )


def _hero(name: str, classes: list[str], talents: list[str]) -> Card:
    return _card(
        uid=f"hero-{name.lower().replace(' ', '-').replace(',', '')}",
        classes=classes,
        talents=talents,
        object_type="hero",
        name=name,
    )


@pytest.fixture(scope="module")
def cases_data() -> dict[str, Any]:
    result: dict[str, Any] = json.loads(CASES_PATH.read_text())
    return result


@pytest.fixture(scope="module")
def heroes(cases_data: dict[str, Any]) -> dict[str, Card]:
    return {
        key: _hero(h["name"], h["classes"], h["talents"]) for key, h in cases_data["heroes"].items()
    }


@pytest.fixture(scope="module")
def format_rules(cases_data: dict[str, Any]) -> FormatRules:
    return FormatRules(banned_in_limited=frozenset(cases_data["banned_in_limited"]))


def _case_id(case: dict[str, Any]) -> str:
    return f"{case['hero']}: {case['description'][:60]}"


def _load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text())["cases"]  # type: ignore[no-any-return]


@pytest.mark.parametrize("case", _load_cases(), ids=_case_id)
def test_legality_case(
    case: dict[str, Any],
    heroes: dict[str, Card],
    format_rules: FormatRules,
) -> None:
    hero = heroes[case["hero"]]
    card_data = case["card"]
    card = _card(
        card_data["uid"],
        card_data["classes"],
        card_data["talents"],
        specialization=card_data.get("specialization"),
    )
    assert card_playable_by(card, hero, format_rules) is case["expected"], case["description"]


def test_all_three_heroes_are_covered(cases_data: dict[str, Any]) -> None:
    assert set(cases_data["heroes"].keys()) == {"levia", "malice", "viserai"}
    hero_counts = {h: 0 for h in cases_data["heroes"]}
    for case in cases_data["cases"]:
        hero_counts[case["hero"]] += 1
    assert all(count >= 8 for count in hero_counts.values())


def test_moniker_of_strips_the_comma_suffix() -> None:
    assert moniker_of("Viserai, Between Worlds") == "Viserai"
    assert moniker_of("Viserai, the Forsaken") == "Viserai"
    assert moniker_of("Levia") == "Levia"
    assert moniker_of("Malice") == "Malice"


def test_card_playable_by_rejects_a_non_hero_second_argument() -> None:
    not_a_hero = _card("x", [], [], object_type="deck")
    card = _card("y", [], [])
    with pytest.raises(ValueError, match="object_type='hero'"):
        card_playable_by(card, not_a_hero)


def test_default_format_rules_has_no_bans() -> None:
    hero = _hero("Test Hero", ["Brute"], ["Shadow"])
    card = _card("banned-uid", [], [])
    assert card_playable_by(card, hero) is True


def test_format_rules_banned_card_is_illegal_even_when_default_used() -> None:
    hero = _hero("Test Hero", ["Brute"], ["Shadow"])
    card = _card("banned-uid", [], [])
    rules = FormatRules(banned_in_limited=frozenset({"banned-uid"}))
    assert card_playable_by(card, hero, rules) is False
