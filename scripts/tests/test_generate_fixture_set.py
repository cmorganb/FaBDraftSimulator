"""Tests for the synthetic FIXTURE set (WP-01). This is the test-only count
check described in the plan for this WP - the reusable
`scripts/validate_set.py` CLI gate with `--allow-incomplete` is WP-02, not
built here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from scripts.generate_fixture_set import (
    MAJESTIC_CORE,
    MAJESTIC_EXPANSION,
    RARITY_COUNTS,
    build_fixture_set,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"
FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "fixture_set.json"


def _registry() -> Registry[Any]:
    resources: list[tuple[str, Resource[Any]]] = []
    for path in sorted(CONTRACTS_DIR.glob("*.schema.json")):
        contents = json.loads(path.read_text())
        resources.append((path.name, Resource.from_contents(contents)))
    return Registry().with_resources(resources)


def test_rarity_counts_match_real_iar_data() -> None:
    # plan section 2.4's own S4 table is wrong (see docs/status/BLOCKED.md):
    # it overstated Marvel (27 vs. real 3) and Basic (16 vs. real 14), and
    # slightly overstated Legendary (5 vs. real 4). These are the real
    # numbers, confirmed against a Card Vault export of IAR and ingested via
    # scripts/ingest_cardvault.py (see docs/status/WP-05.md's amendment).
    assert RARITY_COUNTS == {"F": 2, "V": 3, "L": 4, "M": 40, "R": 66, "C": 133, "B": 14}
    assert sum(RARITY_COUNTS.values()) == 262
    assert RARITY_COUNTS["M"] == MAJESTIC_CORE + MAJESTIC_EXPANSION


def test_generated_snapshot_matches_expected_counts_exactly() -> None:
    snapshot = build_fixture_set()
    assert len(snapshot.cards) == 262
    for rarity, expected in RARITY_COUNTS.items():
        actual = sum(1 for c in snapshot.cards if c.rarity == rarity)
        assert actual == expected, f"rarity {rarity}: expected {expected}, got {actual}"
    assert snapshot.integrity.counts_match is True


def test_generated_snapshot_has_unique_uids_and_card_numbers() -> None:
    snapshot = build_fixture_set()
    uids = [c.uid for c in snapshot.cards]
    numbers = [c.card_number for c in snapshot.cards]
    assert len(set(uids)) == len(uids)
    assert len(set(numbers)) == len(numbers)


def test_generated_snapshot_has_three_heroes_with_weapon_and_arm_equipment() -> None:
    snapshot = build_fixture_set()
    heroes = [c for c in snapshot.cards if c.object_type == "hero"]
    arena_cards = [c for c in snapshot.cards if c.object_type == "arena" and c.rarity == "B"]
    weapons = [c for c in arena_cards if "Weapon" in c.types]
    arms = [c for c in arena_cards if c.equipment_slot == "arms"]
    assert len(heroes) == 3
    assert len(weapons) == 3
    assert len(arms) == 3
    assert all(c.rarity == "B" for c in heroes)  # plan S10: basic-rarity weapon + arm
    assert all(c.rarity == "B" for c in arena_cards)
    # the fixture also includes non-Basic-rarity equipment (pack-eligible,
    # unlike the heroes' own gear) - see scripts/generate_fixture_set.py.
    non_basic_arena = [c for c in snapshot.cards if c.object_type == "arena" and c.rarity != "B"]
    assert len(non_basic_arena) == 2


def test_expansion_majestics_are_not_draftable_and_core_ones_are() -> None:
    snapshot = build_fixture_set()
    majestics = [c for c in snapshot.cards if c.rarity == "M"]
    draftable = [c for c in majestics if c.draftable]
    non_draftable = [c for c in majestics if not c.draftable]
    assert len(draftable) == MAJESTIC_CORE
    assert len(non_draftable) == MAJESTIC_EXPANSION


def test_fixture_set_json_on_disk_validates_against_set_schema() -> None:
    """The committed data/fixtures/fixture_set.json (produced by
    `uv run python scripts/generate_fixture_set.py`) must validate as-is -
    this catches serialization bugs like forgetting `by_alias=True` that a
    pure in-memory model test would miss.
    """
    instance = json.loads(FIXTURE_PATH.read_text())
    schema = json.loads((CONTRACTS_DIR / "set.schema.json").read_text())
    validator = Draft202012Validator(schema, registry=_registry())
    validator.validate(instance)
    assert instance["expected_counts"]["total"] == 262
    assert set(instance["expected_counts"].keys()) == {
        "total",
        "F",
        "V",
        "L",
        "M",
        "R",
        "C",
        "B",
    }
