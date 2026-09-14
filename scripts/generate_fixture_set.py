#!/usr/bin/env python3
"""Generate a synthetic 263-card* fixture set with the same shape as IAR
(plan section 2.5, WP-01), so every downstream WP can develop and test
against `FIXTURE` with zero dependency on real (unreleased, IP-restricted)
card data.

* See docs/status/WP-01.md and docs/status/BLOCKED.md: plan section 2.4's S3
("Set size: 263 cards") does not match the sum of S4's own rarity split
(2+27+5+40+66+133+16 = 289, not 263). This generator matches the
itemized, internally-consistent S4 breakdown (total 289) rather than the
S3 headline figure, and flags the discrepancy for human resolution against
the official IAR product page rather than silently picking one number.

Usage:
    uv run python scripts/generate_fixture_set.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fabdraft_core.contracts import Card, SetSnapshot

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "data" / "fixtures"
CONFIG_DIR = REPO_ROOT / "data" / "config"

SET_CODE = "FIXTURE"

# Matches plan section 2.4 S4's itemized rarity split (see module docstring
# re: the S3/S4 total mismatch).
RARITY_COUNTS: dict[str, int] = {
    "F": 2,
    "V": 27,
    "L": 5,
    "M": 40,  # 20 core (draftable) + 20 expansion (non-draftable extra slot, S13)
    "R": 66,
    "C": 133,
    "B": 16,  # includes 3 heroes + 3 weapons + 3 arm equipment, see build_heroes()
}
MAJESTIC_CORE = 20
MAJESTIC_EXPANSION = 20

# Draftable-by-rarity, mirroring plan section 5.4's slot design (WP-05 will
# recompute this dynamically per pack; this is the static default).
NON_DRAFTABLE_RARITIES = {"B", "V", "F"}  # L and M(expansion) handled per-card below

FIXTURE_HEROES: list[dict[str, Any]] = [
    {"name": "Fixture Hero Brute", "classes": ["Brute"]},
    {"name": "Fixture Hero Necromancer", "classes": ["Necromancer"]},
    {"name": "Fixture Hero Runeblade", "classes": ["Runeblade"]},
]
TALENT = "Shadow"  # all three real IAR heroes are Shadow-talent (plan S10)

ARCHETYPES: list[dict[str, Any]] = [
    {"classes": [], "talents": []},
    {"classes": [], "talents": [TALENT]},
    {"classes": ["Brute"], "talents": [TALENT]},
    {"classes": ["Necromancer"], "talents": [TALENT]},
    {"classes": ["Runeblade"], "talents": [TALENT]},
]

_counter = 0


def _next_number() -> str:
    global _counter
    _counter += 1
    return f"FIXTURE{_counter:03d}"


def _deck_card(rarity: str, index: int, *, draftable: bool) -> Card:
    archetype = ARCHETYPES[index % len(ARCHETYPES)]
    pitch = (index % 3) + 1
    name = f"Fixture {rarity} Card {index:03d}"
    keywords = ["Blood Debt"] if index % 7 == 0 else []
    types = ["Action", "Attack"] if index % 2 == 0 else ["Action"]
    return Card(
        uid=f"fixture-{rarity.lower()}-card-{index:03d}-{pitch}",
        set_code=SET_CODE,
        card_number=_next_number(),
        name=name,
        pitch=pitch,  # type: ignore[arg-type]
        rarity=rarity,  # type: ignore[arg-type]
        types=types,
        classes=archetype["classes"],
        talents=archetype["talents"],
        subtypes=[],
        cost=index % 4,
        power=2 + (index % 5),
        defense=1 + (index % 4),
        life=None,
        intellect=None,
        keywords=keywords,
        functional_text=(
            "When this hits, create a Gate to i'Arathael token." if index % 11 == 0 else ""
        ),
        specialization=None,
        is_deck_card=True,
        is_arena_card=False,
        equipment_slot=None,
        hands=None,
        image_url=None,
        double_faced_with=None,
        draftable=draftable,
        data_complete=True,
    )


def build_generic_deck_cards() -> list[Card]:
    cards: list[Card] = []
    for i in range(RARITY_COUNTS["C"]):
        cards.append(_deck_card("C", i, draftable=True))
    for i in range(RARITY_COUNTS["R"]):
        cards.append(_deck_card("R", i, draftable=True))
    for i in range(MAJESTIC_CORE):
        cards.append(_deck_card("M", i, draftable=True))
    for i in range(MAJESTIC_CORE, MAJESTIC_CORE + MAJESTIC_EXPANSION):
        cards.append(_deck_card("M", i, draftable=False))
    for i in range(RARITY_COUNTS["L"]):
        cards.append(_deck_card("L", i, draftable=False))
    for i in range(RARITY_COUNTS["V"]):
        cards.append(_deck_card("V", i, draftable=False))
    for i in range(RARITY_COUNTS["F"]):
        cards.append(_deck_card("F", i, draftable=False))
    return cards


def build_heroes() -> list[Card]:
    """3 young heroes + their basic weapon + basic arm equipment (plan S10),
    plus generic basics to fill out the Basic-rarity count (16).
    """
    cards: list[Card] = []
    for hero in FIXTURE_HEROES:
        hero_classes = hero["classes"]
        cards.append(
            Card(
                uid=f"{hero['name'].lower().replace(' ', '-')}-none",
                set_code=SET_CODE,
                card_number=_next_number(),
                name=hero["name"],
                pitch=None,
                rarity="B",
                types=["Hero", "Young"],
                classes=hero_classes,
                talents=[TALENT],
                subtypes=[],
                cost=None,
                power=None,
                defense=None,
                life=20,
                intellect=4,
                keywords=[],
                functional_text="",
                specialization=None,
                is_deck_card=False,
                is_arena_card=True,
                equipment_slot=None,
                hands=None,
                image_url=None,
                double_faced_with=None,
                draftable=False,
                data_complete=True,
            )
        )
        cards.append(
            Card(
                uid=f"{hero['name'].lower().replace(' ', '-')}-weapon-none",
                set_code=SET_CODE,
                card_number=_next_number(),
                name=f"{hero['name']}'s Blade",
                pitch=None,
                rarity="B",
                types=["Weapon", "One Hand"],
                classes=hero_classes,
                talents=[TALENT],
                subtypes=[],
                cost=None,
                power=3,
                defense=None,
                life=None,
                intellect=None,
                keywords=[],
                functional_text="",
                specialization=hero["name"],
                is_deck_card=False,
                is_arena_card=True,
                equipment_slot=None,
                hands=1,
                image_url=None,
                double_faced_with=None,
                draftable=False,
                data_complete=True,
            )
        )
        cards.append(
            Card(
                uid=f"{hero['name'].lower().replace(' ', '-')}-armguard-none",
                set_code=SET_CODE,
                card_number=_next_number(),
                name=f"{hero['name']}'s Armguard",
                pitch=None,
                rarity="B",
                types=["Arms"],
                classes=hero_classes,
                talents=[TALENT],
                subtypes=[],
                cost=None,
                power=None,
                defense=1,
                life=None,
                intellect=None,
                keywords=[],
                functional_text="",
                specialization=hero["name"],
                is_deck_card=False,
                is_arena_card=True,
                equipment_slot="arms",
                hands=None,
                image_url=None,
                double_faced_with=None,
                draftable=False,
                data_complete=True,
            )
        )

    generic_basics_needed = RARITY_COUNTS["B"] - len(cards)
    for i in range(generic_basics_needed):
        cards.append(
            Card(
                uid=f"fixture-generic-basic-{i:02d}-none",
                set_code=SET_CODE,
                card_number=_next_number(),
                name=f"Fixture Generic Basic {i:02d}",
                pitch=None,
                rarity="B",
                types=["Action"],
                classes=[],
                talents=[],
                subtypes=[],
                cost=1,
                power=2,
                defense=2,
                life=None,
                intellect=None,
                keywords=[],
                functional_text="",
                specialization=None,
                is_deck_card=True,
                is_arena_card=False,
                equipment_slot=None,
                hands=None,
                image_url=None,
                double_faced_with=None,
                draftable=False,
                data_complete=True,
            )
        )
    return cards


def build_fixture_set() -> SetSnapshot:
    cards = build_generic_deck_cards() + build_heroes()
    counts: dict[str, int] = {"total": len(cards)}
    for rarity in ("F", "V", "L", "M", "R", "C", "B"):
        counts[rarity] = sum(1 for c in cards if c.rarity == rarity)

    return SetSnapshot(
        set_code=SET_CODE,
        name="Fixture Set (synthetic, shaped like IAR)",
        release_date="1970-01-01",  # type: ignore[arg-type]
        source={  # type: ignore[arg-type]
            "provider": "synthetic",
            "commit": "n/a",
            "retrieved_at": "1970-01-01T00:00:00Z",
        },
        expected_counts=counts,  # type: ignore[arg-type]
        cards=cards,
        integrity={"counts_match": True, "incomplete_cards": []},  # type: ignore[arg-type]
    )


def write_expected_counts(snapshot: SetSnapshot) -> None:
    counts = {
        "total": len(snapshot.cards),
        "F": RARITY_COUNTS["F"],
        "V": RARITY_COUNTS["V"],
        "L": RARITY_COUNTS["L"],
        "M": RARITY_COUNTS["M"],
        "R": RARITY_COUNTS["R"],
        "C": RARITY_COUNTS["C"],
        "B": RARITY_COUNTS["B"],
    }
    (CONFIG_DIR / "fixture.expected_counts.json").write_text(json.dumps(counts, indent=2) + "\n")


def write_pack_config() -> None:
    config = {
        "set_code": SET_CODE,
        "pack_size": 16,
        "slots": [
            {"id": "common", "count": 11, "rarities": {"C": 1.0}, "draftable": True},
            {"id": "rare", "count": 1, "rarities": {"R": 1.0}, "draftable": True},
            {
                "id": "rare_or_majestic",
                "count": 1,
                "rarities": {"R": 0.5, "M": 0.5},
                "majestic_subset": "core",
                "draftable": True,
                "confidence": "ESTIMATED",
            },
            {
                "id": "rainbow_foil",
                "count": 1,
                "rarities": {"C": 0.75, "R": 0.20, "M": 0.05},
                "foiling": "RF",
                "draftable": True,
                "confidence": "ESTIMATED",
            },
            {"id": "basic", "count": 1, "rarities": {"B": 1.0}, "draftable": False},
            {
                "id": "chase",
                "count": 1,
                "rarities": {
                    "B": 0.62,
                    "M_expansion": 0.20,
                    "L": 0.08,
                    "V": 0.07,
                    "F": 0.01,
                    "CF": 0.02,
                },
                "draftable": False,
                "confidence": "ESTIMATED",
            },
        ],
        "no_duplicate_uids_within_pack": True,
        "cold_foil_rate_per_pack": 0.0417,
    }
    (CONFIG_DIR / "fixture.pack_config.json").write_text(json.dumps(config, indent=2) + "\n")


def write_format_config() -> None:
    config = {
        "set_code": SET_CODE,
        "deck_size": 30,
        "deck_size_mode": "exact",
        "heroes": [
            {
                "uid": f"{h['name'].lower().replace(' ', '-')}-none",
                "name": h["name"],
                "classes": h["classes"],
                "talents": [TALENT],
                "basic_weapon_uids": [f"{h['name'].lower().replace(' ', '-')}-weapon-none"],
                "basic_equipment_uids": [f"{h['name'].lower().replace(' ', '-')}-armguard-none"],
            }
            for h in FIXTURE_HEROES
        ],
        "basic_pool_unlimited": True,
        "allow_prerelease_hero": False,
        "format_restrictions": [],
        "notes": "Synthetic fixture mirroring plan section 5.3's iar.format.json shape.",
    }
    (CONFIG_DIR / "fixture.format.json").write_text(json.dumps(config, indent=2) + "\n")


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    snapshot = build_fixture_set()
    (FIXTURES_DIR / "fixture_set.json").write_text(
        json.dumps(snapshot.model_dump(mode="json", by_alias=True), indent=2) + "\n"
    )
    write_expected_counts(snapshot)
    write_pack_config()
    write_format_config()
    print(f"Wrote {len(snapshot.cards)} cards to {FIXTURES_DIR / 'fixture_set.json'}")


if __name__ == "__main__":
    main()
