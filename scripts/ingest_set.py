#!/usr/bin/env python3
"""Ingest a set from the the-fab-cube/flesh-and-blood-cards open dataset into
a fabdraft_core.contracts.SetSnapshot (plan section 5.2, WP-01).

Never guesses at missing or ambiguous required data: raises
fabdraft_core.errors.DataIncompleteError instead (plan section 0 item 3).

As of 2026-09-14 the upstream `IAR` set entry is a placeholder with no card
rows (checked against the pinned commit machinery below) - this script is
written against the *real* upstream JSON schema (confirmed via
https://the-fab-cube.github.io/flesh-and-blood-cards/web/json-schemas/card-schema.html)
so it is ready to run once IAR data lands, but it cannot be exercised
end-to-end yet. Its mapping logic is unit tested against a small fictional
mock payload shaped like the real schema (scripts/tests/fixtures/) - never
real Legend Story Studios card text.

Usage:
    uv run python scripts/ingest_set.py --set-code IAR --commit <sha> \\
        --out data/sets/IAR.json

    # offline / test mode, reads local files instead of the network:
    uv run python scripts/ingest_set.py --set-code IAR \\
        --card-json path/to/card.json --set-json path/to/set.json \\
        --out /tmp/IAR.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fabdraft_core.contracts import Card, SetSnapshot
from fabdraft_core.errors import DataIncompleteError

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REPO = "the-fab-cube/flesh-and-blood-cards"
DEFAULT_BRANCH_OR_COMMIT = "develop"  # callers should pin an actual commit sha for reproducibility


def raw_url(commit: str, path: str, repo: str = DEFAULT_REPO) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"


# --- Rarity mapping ---------------------------------------------------------
#
# Confirmed from https://raw.githubusercontent.com/the-fab-cube/flesh-and-blood-cards/develop/documentation/abbreviations.md
# (retrieved 2026-09-14): C=Common, R=Rare, S=Super Rare, M=Majestic,
# L=Legendary, F=Fabled, T=Token, V=Marvel, P=Promo.
#
# "B" for Basic rarity is NOT explicitly listed in that document (possibly an
# omission in the summarized fetch). It is included here as an inferred
# mapping - B is the only single-letter code consistent with the rest of the
# scheme that isn't already taken - but is NOT independently confirmed.
# See docs/status/BLOCKED.md. Any other code raises loudly rather than
# guessing.
RARITY_MAP: dict[str, str] = {
    "C": "C",
    "R": "R",
    "M": "M",
    "L": "L",
    "F": "F",
    "V": "V",
    "B": "B",  # VERIFY: inferred, not confirmed against a real Basic-rarity card.
}
# Deliberately excluded (not draftable-set rarities in our domain, plan
# section 5.1's enum is B/C/R/M/L/V/F only): "S" Super Rare, "T" Token,
# "P" Promo.

# --- Class / talent classification ------------------------------------------
#
# The upstream schema has no separate classes/talents fields (confirmed via
# the card-schema doc) - they must be derived from `types`. This list is
# best-effort general FaB game knowledge, NOT sourced from a machine-readable
# spec, and must be reconciled against the official IAR hero list
# (plan S10: Levia/Brute, Malice/Necromancer, Viserai/Runeblade, all Shadow)
# before being trusted for anything beyond the fixture set. A card whose type
# line contains a token this script cannot classify is marked
# data_complete=False rather than silently miscategorized.
KNOWN_CLASSES: set[str] = {
    "Assassin",
    "Brute",
    "Guardian",
    "Illusionist",
    "Mechanologist",
    "Merchant",
    "Ninja",
    "Ranger",
    "Runeblade",
    "Shapeshifter",
    "Warrior",
    "Wizard",
    "Necromancer",
    "Bard",
    "Pirate",
    "Adjudicator",
}
KNOWN_TALENTS: set[str] = {
    "Light",
    "Shadow",
    "Chaos",
    "Elemental",
    "Mystic",
    "Royal",
    "Draconic",
    "Xenan",
    "Ice",
    "Earth",
    "Lightning",
}
# Types that are structural (not a class, talent, or subtype worth keeping
# verbatim) and should just be dropped from `subtypes`. Equipment/weapon
# descriptors are handled separately by derive_equipment() but still need to
# be excluded here so they don't get flagged as an unclassifiable subtype.
STRUCTURAL_TYPES: set[str] = {
    "Action",
    "Attack",
    "Instant",
    "Reaction",
    "Defense Reaction",
    "Weapon",
    "One Hand",
    "Two Hand",
    "Head",
    "Chest",
    "Arms",
    "Legs",
}

_SPECIALIZATION_RE = re.compile(r"Specialization\s*[:\-]?\s*([A-Z][A-Za-z' ]+?)(?:\.|,|$)")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug


_PITCH_WORD = {1: "red", 2: "yellow", 3: "blue"}


def make_uid(name: str, pitch: int | None) -> str:
    """uid = name + pitch (plan section 5.1: 'a unique card is name + pitch';
    printings are collapsed, so this is stable across reprints).
    """
    word = _PITCH_WORD.get(pitch) if pitch is not None else "none"
    return f"{slugify(name)}-{word}"


def parse_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    stripped = raw.strip()
    if stripped == "" or not re.fullmatch(r"-?\d+", stripped):
        # Variable values ("X", "*", combinations) are a known gap - see
        # docs/status/WP-01.md. Not an error: null is a valid contract value.
        return None
    return int(stripped)


def classify_types(types: list[str]) -> tuple[list[str], list[str], list[str], bool]:
    """Returns (classes, talents, subtypes, fully_classified)."""
    classes: list[str] = []
    talents: list[str] = []
    subtypes: list[str] = []
    fully_classified = True
    for t in types:
        if t in KNOWN_CLASSES:
            classes.append(t)
        elif t in KNOWN_TALENTS:
            talents.append(t)
        elif t in STRUCTURAL_TYPES:
            continue
        else:
            subtypes.append(t)
            fully_classified = False
    return classes, talents, subtypes, fully_classified


def derive_specialization(functional_text_plain: str) -> str | None:
    match = _SPECIALIZATION_RE.search(functional_text_plain)
    if match:
        return match.group(1).strip()
    return None


_EQUIPMENT_SLOTS = {"Head", "Chest", "Arms", "Legs"}


def derive_equipment(types: list[str]) -> tuple[str | None, int | None]:
    equipment_slot = next((t.lower() for t in types if t in _EQUIPMENT_SLOTS), None)
    hands: int | None = None
    if "Weapon" in types:
        if "One Hand" in types or "1H" in types:
            hands = 1
        elif "Two Hand" in types or "2H" in types:
            hands = 2
    return equipment_slot, hands


_DRAFTABLE_RARITIES = {"C", "R"}  # plan section 5.4: common/rare slots are always draftable


def default_draftable(rarity: str, is_expansion_slot: bool) -> bool:
    """A best-effort default per plan section 5.4's pack slot design: common
    and rare are always draftable; a core Majestic is draftable, an
    expansion-slot one is not (S13); Basic/Legendary/Marvel/Fabled only ever
    appear in non-draftable slots. The pack generator (WP-05) still computes
    the *actual* draftability of a drafted instance from the slot it came
    from - this is just a sane default for the static Card record.
    """
    if rarity in _DRAFTABLE_RARITIES:
        return True
    if rarity == "M":
        return not is_expansion_slot
    return False


def map_card(raw_card: dict[str, Any], printing: dict[str, Any], set_code: str) -> Card:
    """Map one (card, printing) pair from the upstream schema to our Card
    contract. Raises DataIncompleteError if a required field is absent.
    """
    name = raw_card.get("name")
    if not name:
        raise DataIncompleteError(f"card {raw_card.get('unique_id')!r} has no name")

    rarity_raw = printing.get("rarity")
    if not rarity_raw:
        raise DataIncompleteError(f"card {name!r} printing {printing.get('id')!r} has no rarity")
    if rarity_raw not in RARITY_MAP:
        raise DataIncompleteError(
            f"card {name!r} printing {printing.get('id')!r} has unmapped rarity code "
            f"{rarity_raw!r} - extend RARITY_MAP in scripts/ingest_set.py deliberately, "
            "do not guess."
        )
    rarity = RARITY_MAP[rarity_raw]

    card_number = printing.get("id")
    if not card_number:
        raise DataIncompleteError(f"card {name!r} has a printing with no id/card_number")

    pitch = parse_int(raw_card.get("pitch"))
    types = list(raw_card.get("types") or [])
    classes, talents, subtypes, fully_classified = classify_types(types)

    functional_text = raw_card.get("functional_text_plain") or raw_card.get("functional_text") or ""
    specialization = derive_specialization(functional_text)
    equipment_slot, hands = derive_equipment(types)

    keywords = sorted(
        set(raw_card.get("card_keywords") or [])
        | set(raw_card.get("ability_and_effect_keywords") or [])
    )

    is_arena_card = bool({"Hero", "Weapon", "Head", "Chest", "Arms", "Legs"} & set(types))
    is_expansion_slot = bool(printing.get("expansion_slot", False))

    data_complete = fully_classified

    return Card(
        uid=make_uid(name, pitch),
        set_code=set_code,
        card_number=card_number,
        name=name,
        pitch=pitch,  # type: ignore[arg-type]
        rarity=rarity,  # type: ignore[arg-type]
        types=types,
        classes=classes,
        talents=talents,
        subtypes=subtypes,
        cost=parse_int(raw_card.get("cost")),
        power=parse_int(raw_card.get("power")),
        defense=parse_int(raw_card.get("defense")),
        life=parse_int(raw_card.get("health")),
        intellect=parse_int(raw_card.get("intelligence")),
        keywords=keywords,
        functional_text=functional_text,
        specialization=specialization,
        is_deck_card=not is_arena_card,
        is_arena_card=is_arena_card,
        equipment_slot=equipment_slot,  # type: ignore[arg-type]
        hands=hands,  # type: ignore[arg-type]
        image_url=printing.get("image_url"),
        double_faced_with=None,  # DFC presence is a VERIFY item for IAR (plan D11/R5); no
        # data to derive it from yet, so this is intentionally left unset rather than guessed.
        draftable=default_draftable(rarity, is_expansion_slot),
        is_expansion_slot=is_expansion_slot,
        data_complete=data_complete,
    )


def cards_for_set(raw_cards: list[dict[str, Any]], set_code: str) -> list[Card]:
    """Every (card, printing) pair whose printing.set_id == set_code."""
    mapped: list[Card] = []
    for raw_card in raw_cards:
        for printing in raw_card.get("printings") or []:
            if printing.get("set_id") == set_code:
                mapped.append(map_card(raw_card, printing, set_code))
    return mapped


def build_snapshot(
    raw_cards: list[dict[str, Any]],
    set_code: str,
    set_name: str,
    release_date: str,
    expected_counts: dict[str, int],
    source_commit: str,
    provider: str = "the-fab-cube",
) -> SetSnapshot:
    cards = cards_for_set(raw_cards, set_code)
    if not cards:
        raise DataIncompleteError(
            f"no cards found for set_code={set_code!r} - upstream data for this set "
            "may not be published yet (see plan risk R1 / docs/status/BLOCKED.md)."
        )
    counts: dict[str, int] = {"total": len(cards)}
    for rarity in ("F", "V", "L", "M", "R", "C", "B"):
        counts[rarity] = sum(1 for c in cards if c.rarity == rarity)
    incomplete = [c.uid for c in cards if not c.data_complete]

    return SetSnapshot(
        set_code=set_code,
        name=set_name,
        release_date=release_date,  # type: ignore[arg-type]
        source={  # type: ignore[arg-type]
            "provider": provider,
            "commit": source_commit,
            "retrieved_at": datetime.now(UTC).isoformat(),
        },
        expected_counts=expected_counts,  # type: ignore[arg-type]
        cards=cards,
        integrity={  # type: ignore[arg-type]
            "counts_match": counts == expected_counts,
            "incomplete_cards": incomplete,
        },
    )


def load_expected_counts(set_code: str, config_dir: Path | None = None) -> dict[str, int]:
    config_dir = config_dir or (REPO_ROOT / "data" / "config")
    config_path = config_dir / f"{set_code.lower()}.expected_counts.json"
    if not config_path.exists():
        raise DataIncompleteError(
            f"no expected_counts config for set_code={set_code!r} at {config_path} - "
            "add one from the official rarity split before ingesting; never inferred."
        )
    result: dict[str, int] = json.loads(config_path.read_text())
    return result


def fetch(url: str) -> Any:
    import httpx

    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-code", required=True)
    parser.add_argument("--set-name", default=None, help="Falls back to the set_code if omitted")
    parser.add_argument("--release-date", default="1970-01-01")
    parser.add_argument("--commit", default=DEFAULT_BRANCH_OR_COMMIT)
    parser.add_argument(
        "--card-json", type=Path, default=None, help="Local file instead of network fetch"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.card_json:
        raw_cards = json.loads(args.card_json.read_text())
    else:
        raw_cards = fetch(raw_url(args.commit, "json/english/card.json"))

    expected_counts = load_expected_counts(args.set_code)
    snapshot = build_snapshot(
        raw_cards=raw_cards,
        set_code=args.set_code,
        set_name=args.set_name or args.set_code,
        release_date=args.release_date,
        expected_counts=expected_counts,
        source_commit=args.commit,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot.model_dump(mode="json", by_alias=True), indent=2))
    print(f"Wrote {len(snapshot.cards)} cards to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
