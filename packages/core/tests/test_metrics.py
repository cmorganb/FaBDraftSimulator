"""Tests for pool/deck metrics (WP-10, plan section 6.4)."""

from __future__ import annotations

import json
from pathlib import Path

from fabdraft_core.contracts import Card, SetSnapshot
from fabdraft_core.deck.metrics import (
    attack_action_count,
    average_power,
    compute_pool_shape,
    cost_curve,
    defense_profile,
    equipment_coverage_by_slot,
    go_again_density,
    hero_playable_counts,
    iar_tag_counts,
    pitch_distribution,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_SET_PATH = REPO_ROOT / "data" / "fixtures" / "fixture_set.json"
FIXTURE_FORMAT_PATH = REPO_ROOT / "data" / "config" / "fixture.format.json"


def _card(
    uid: str,
    *,
    pitch: int | None = 1,
    cost: int | None = 1,
    power: int | None = 2,
    defense: int | None = 2,
    types: list[str] | None = None,
    classes: list[str] | None = None,
    talents: list[str] | None = None,
    functional_text: str = "",
    keywords: list[str] | None = None,
    object_type: str = "deck",
    equipment_slot: str | None = None,
) -> Card:
    return Card(
        uid=uid,
        set_code="FIXTURE",
        card_number=uid.upper(),
        name=uid,
        pitch=pitch,
        rarity="C",
        types=types or ["Action"],
        classes=classes or [],
        talents=talents or [],
        subtypes=[],
        cost=cost,
        power=power,
        defense=defense,
        life=None,
        intellect=None,
        keywords=keywords or [],
        functional_text=functional_text,
        specialization=None,
        object_type=object_type,  # type: ignore[arg-type]
        is_deck_card=object_type == "deck",
        is_arena_card=object_type == "arena",
        equipment_slot=equipment_slot,  # type: ignore[arg-type]
        hands=None,
        image_url=None,
        double_faced_with=None,
        draftable=True,
        is_expansion_slot=False,
        data_complete=True,
    )


def _hero(name: str, *, classes: list[str], talents: list[str]) -> Card:
    return _card(
        f"hero-{name.lower()}",
        pitch=None,
        cost=None,
        power=None,
        defense=None,
        classes=classes,
        talents=talents,
        types=["Hero"],
        object_type="hero",
    )


def test_pitch_distribution_excludes_pitchless_cards() -> None:
    cards = [_card("a", pitch=1), _card("b", pitch=1), _card("c", pitch=3), _card("d", pitch=None)]
    assert pitch_distribution(cards) == {1: 2, 3: 1}


def test_cost_curve_excludes_variable_cost_cards() -> None:
    cards = [_card("a", cost=0), _card("b", cost=1), _card("c", cost=1), _card("d", cost=None)]
    assert cost_curve(cards) == {0: 1, 1: 2}


def test_attack_action_count() -> None:
    cards = [
        _card("a", types=["Action", "Attack"]),
        _card("b", types=["Action"]),
        _card("c", types=["Action", "Attack"]),
    ]
    assert attack_action_count(cards) == 2


def test_average_power_ignores_none_and_handles_empty() -> None:
    assert average_power([_card("a", power=2), _card("b", power=4)]) == 3.0
    assert average_power([_card("a", power=None)]) is None
    assert average_power([]) is None


def test_defense_profile() -> None:
    cards = [
        _card("a", pitch=3, defense=3),
        _card("b", pitch=1, defense=3),
        _card("c", pitch=3, defense=1),
        _card("d", pitch=2, defense=None),
    ]
    profile = defense_profile(cards)
    assert profile.defense_3_count == 2
    assert profile.average_defense == (3 + 3 + 1) / 3
    assert profile.blue_block_count == 2  # pitch-3 cards with a defense value: a, c


def test_go_again_density_empty_list_is_zero_not_an_error() -> None:
    assert go_again_density([]) == 0.0


def test_go_again_density() -> None:
    cards = [
        _card("a", functional_text="**Go Again**"),
        _card("b", functional_text="No keyword here."),
    ]
    assert go_again_density(cards) == 0.5


def test_equipment_coverage_by_slot() -> None:
    cards = [
        _card("a", object_type="arena", equipment_slot="head"),
        _card("b", object_type="arena", equipment_slot="head"),
        _card("c", object_type="arena", equipment_slot="arms"),
        _card("d", object_type="deck"),
    ]
    assert equipment_coverage_by_slot(cards) == {
        "head": 2,
        "chest": 0,
        "arms": 1,
        "legs": 0,
    }


def test_iar_tag_counts_aggregates_each_tag() -> None:
    cards = [
        _card("a", keywords=["Blood Debt"]),
        _card("b", functional_text="Create a Gate to i'Arathael token."),
        _card("c", functional_text="No tags here."),
    ]
    counts = iar_tag_counts(cards)
    assert counts["blood_debt"] == 1
    assert counts["gate_generators"] == 1
    assert counts["banished_zone_payoffs"] == 0
    assert counts["usurp_enablers"] == 0
    assert counts["runechant_generators"] == 0


def test_hero_playable_counts_reuses_card_playable_by() -> None:
    brute = _hero("brute", classes=["Brute"], talents=["Shadow"])
    necromancer = _hero("necromancer", classes=["Necromancer"], talents=["Shadow"])
    pool = [
        _card("generic", classes=[], talents=[]),
        _card("brute-only", classes=["Brute"], talents=[]),
        _card("shadow-only", classes=[], talents=["Shadow"]),
        _card("wrong-class", classes=["Ninja"], talents=[]),
    ]
    counts = hero_playable_counts(pool, [brute, necromancer])
    # generic + brute-only + shadow-only legal for brute; wrong-class isn't
    assert counts[brute.uid] == 3
    # generic + shadow-only legal for necromancer; brute-only and
    # wrong-class aren't
    assert counts[necromancer.uid] == 2


def test_compute_pool_shape_end_to_end_against_real_fixture_heroes() -> None:
    snapshot = SetSnapshot.model_validate(json.loads(FIXTURE_SET_PATH.read_text()))
    fmt = json.loads(FIXTURE_FORMAT_PATH.read_text())
    hero_uids = {h["uid"] for h in fmt["heroes"]}
    heroes = [c for c in snapshot.cards if c.uid in hero_uids]
    assert len(heroes) == 3

    pool = [c for c in snapshot.cards if c.is_deck_card][:50]
    shape = compute_pool_shape(pool, heroes)

    assert shape.card_count == len(pool)
    assert set(shape.hero_playable_counts.keys()) == hero_uids
    assert all(count >= 0 for count in shape.hero_playable_counts.values())
    assert sum(shape.pitch_distribution.values()) <= len(pool)
    assert isinstance(shape.iar_tag_counts, dict)


def test_compute_pool_shape_with_no_heroes_given() -> None:
    shape = compute_pool_shape([_card("a"), _card("b")])
    assert shape.hero_playable_counts == {}
    assert shape.card_count == 2


def test_no_metric_field_name_reads_as_a_rating() -> None:
    """plan section 6.4: metrics are never presented as an authoritative
    rating - enforced here by asserting none of the public field/function
    names in this module use evaluative language.
    """
    from fabdraft_core.deck import metrics as metrics_module

    forbidden_substrings = ("score", "rating", "grade", "rank")
    public_names = [name for name in dir(metrics_module) if not name.startswith("_")]
    for name in public_names:
        lowered = name.lower()
        assert not any(word in lowered for word in forbidden_substrings), name
