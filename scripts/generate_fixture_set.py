#!/usr/bin/env python3
"""Generate a synthetic 262-card fixture set with the same shape as the real
IAR set (plan section 2.5, WP-01), so every downstream WP can develop and
test against `FIXTURE` with zero dependency on real (unreleased-at-plan-
time, IP-restricted) card data.

Rarity counts below are the *real*, confirmed IAR numbers (from a Card Vault
export ingested via scripts/ingest_cardvault.py, see docs/status/WP-05.md's
amendment) - not the plan's own section 2.4 S4 table, which is now known to
be wrong: it overstated Marvel (27 vs. real 3) and Basic (16 vs. real 14),
and slightly overstated Legendary (5 vs. real 4). See docs/status/BLOCKED.md
for the full resolution of that discrepancy.

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

# Real IAR rarity split, confirmed 2026-09-14 against a Card Vault export
# (data/IAR/manifest.json, gitignored - see scripts/ingest_cardvault.py).
RARITY_COUNTS: dict[str, int] = {
    "F": 2,
    "V": 3,
    "L": 4,
    "M": 40,  # 20 core (draftable) + 20 expansion (non-draftable extra slot, S13)
    "R": 66,
    "C": 133,
    "B": 14,  # 3 heroes + 3 weapons + 3 arm equipment + 5 generic basics
}
MAJESTIC_CORE = 20
MAJESTIC_EXPANSION = 20

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


def _deck_card(
    rarity: str,
    index: int,
    *,
    draftable: bool,
    is_expansion_slot: bool = False,
    object_type: str = "deck",
) -> Card:
    """A normal deck card, or (when `object_type="arena"`) an illustrative
    non-Basic-rarity equipment piece - real IAR data shows equipment isn't
    always Basic rarity/excluded from packs, only the young heroes' own
    dedicated weapon+arm-equipment is (see fabdraft_core.packs.generator.
    is_pack_eligible and docs/status/WP-05.md's amendment).
    """
    archetype = ARCHETYPES[index % len(ARCHETYPES)]
    is_arena = object_type == "arena"
    pitch = None if is_arena else (index % 3) + 1
    name = f"Fixture {rarity} {'Equipment' if is_arena else 'Card'} {index:03d}"
    keywords = [] if is_arena else (["Blood Debt"] if index % 7 == 0 else [])
    types = ["Equipment"] if is_arena else (["Action", "Attack"] if index % 2 == 0 else ["Action"])
    return Card(
        uid=f"fixture-{rarity.lower()}-{'equip' if is_arena else 'card'}-{index:03d}",
        set_code=SET_CODE,
        card_number=_next_number(),
        name=name,
        pitch=pitch,
        rarity=rarity,  # type: ignore[arg-type]
        types=types,
        classes=[] if is_arena else archetype["classes"],
        talents=[] if is_arena else archetype["talents"],
        subtypes=["Arms"] if is_arena else [],
        cost=None if is_arena else index % 4,
        power=None if is_arena else 2 + (index % 5),
        defense=1 if is_arena else 1 + (index % 4),
        life=None,
        intellect=None,
        keywords=keywords,
        functional_text=(
            "When this hits, create a Gate to i'Arathael token."
            if (not is_arena and index % 11 == 0)
            else ""
        ),
        specialization=None,
        object_type=object_type,  # type: ignore[arg-type]
        is_deck_card=not is_arena,
        is_arena_card=is_arena,
        equipment_slot="arms" if is_arena else None,
        hands=None,
        image_url=None,
        double_faced_with=None,
        draftable=draftable,
        is_expansion_slot=is_expansion_slot,
        data_complete=True,
    )


def build_generic_deck_cards() -> list[Card]:
    cards: list[Card] = []
    # Commons: all generic deck cards except one illustrative Common
    # equipment piece (pack-eligible, unlike the Basic-rarity hero gear).
    for i in range(RARITY_COUNTS["C"] - 1):
        cards.append(_deck_card("C", i, draftable=True))
    cards.append(_deck_card("C", RARITY_COUNTS["C"] - 1, draftable=True, object_type="arena"))

    for i in range(RARITY_COUNTS["R"]):
        cards.append(_deck_card("R", i, draftable=True))
    for i in range(MAJESTIC_CORE):
        cards.append(_deck_card("M", i, draftable=True))
    for i in range(MAJESTIC_CORE, MAJESTIC_CORE + MAJESTIC_EXPANSION):
        cards.append(_deck_card("M", i, draftable=False, is_expansion_slot=True))

    # Legendary: same idea - one illustrative Legendary equipment piece,
    # still non-draftable (chase-slot only) but via the L rarity, not
    # because it's an arena card.
    for i in range(RARITY_COUNTS["L"] - 1):
        cards.append(_deck_card("L", i, draftable=False))
    cards.append(_deck_card("L", RARITY_COUNTS["L"] - 1, draftable=False, object_type="arena"))

    for i in range(RARITY_COUNTS["V"]):
        cards.append(_deck_card("V", i, draftable=False))
    for i in range(RARITY_COUNTS["F"]):
        cards.append(_deck_card("F", i, draftable=False))
    return cards


def build_heroes() -> list[Card]:
    """3 young heroes (object_type="hero", never pack-eligible regardless of
    rarity) + their Basic-rarity weapon + arm equipment (object_type="arena",
    plan S10), plus generic Basic deck cards to fill out the Basic-rarity
    count.
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
                object_type="hero",
                is_deck_card=False,
                is_arena_card=False,
                equipment_slot=None,
                hands=None,
                image_url=None,
                double_faced_with=None,
                draftable=False,
                is_expansion_slot=False,
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
                object_type="arena",
                is_deck_card=False,
                is_arena_card=True,
                equipment_slot=None,
                hands=1,
                image_url=None,
                double_faced_with=None,
                draftable=False,
                is_expansion_slot=False,
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
                object_type="arena",
                is_deck_card=False,
                is_arena_card=True,
                equipment_slot="arms",
                hands=None,
                image_url=None,
                double_faced_with=None,
                draftable=False,
                is_expansion_slot=False,
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
                object_type="deck",
                is_deck_card=True,
                is_arena_card=False,
                equipment_slot=None,
                hands=None,
                image_url=None,
                double_faced_with=None,
                draftable=False,
                is_expansion_slot=False,
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
        name="Fixture Set (synthetic, shaped like the real IAR set)",
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
