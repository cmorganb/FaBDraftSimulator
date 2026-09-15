#!/usr/bin/env python3
"""Ingest a set from a Card Vault (cardvault.fabtcg.com) export directory
into a fabdraft_core.contracts.SetSnapshot (plan section 5.2, WP-01/WP-05).

This is a second, independent ingestion path alongside scripts/ingest_set.py
(which targets the the-fab-cube GitHub dataset - still an unpopulated
placeholder for IAR as of 2026-09-14, see docs/status/BLOCKED.md). Real IAR
card data *is* now available via a Card Vault export at `data/IAR/`
(gitignored - real Legend Story Studios card text/images are never
committed, plan section 11).

Schema (confirmed by directly inspecting data/IAR/cards.json, 2026-09-14 -
never assumed):
    manifest.json: {"metadata": {set_code, generated_at, source_url,
        card_count, rarity_counts: {fabled, basic, majestic, rare, common,
        legendary, marvel}, ...}, "images": [...]}
    cards.json: {"metadata": {...}, "cards": [<card>, ...]}
    <card>: {card_id, name, set_code, language, object_type, card_type,
             default_print_id, rarity, faces: [<face>, ...],
             printings: [<printing>, ...], rulings_errata, legality,
             source_url}
        object_type: "deck-card" | "arena-card" | "hero-card" | "token"
        rarity: "common" | "rare" | "majestic" | "legendary" | "marvel" |
                "fabled" | "basic"
    <printing>: {print_id, set_number, rarity, layout, product, is_default,
                 faces: [<face>, ...]}
    <face>: {face_id, name, typebox, text, text_raw, text_html,
             core_text_raw, flavor_text, artist, color, orientation,
             art_type, finish_type, image_urls: {small, normal, large},
             image_path, pitch, cost, power, defense, intellect, life,
             classes, talents, types, subtypes}

`card_id` already uniquely identifies a name+pitch card (printings are
pre-collapsed by the exporter) and is used directly as `Card.uid`.

Notable findings from the real IAR export, each with an unambiguous
in-data signal - see docs/status/WP-05.md's amendment for detail:
  - `classes` sometimes contains the literal string "Generic" instead of
    an empty list - normalized to [] here to match our own contract
    convention (plan section 5.1: "classes: [] means Generic").
  - `pitch` is not always 1-3 (one Fabled resource has pitch 4) - the Card
    contract no longer restricts this.
  - IAR *does* contain double-faced cards (`card_type: "flip-card"`), but
    only on the 2 non-young/adult hero forms (Viserai's "Usurper" back
    face). Since heroes are never drafted (S10), plan D11's face-down-pile
    DFC-hiding rule never actually triggers for IAR limited - resolves
    VERIFY item R5/D11. The back face is intentionally not modeled here
    (`double_faced_with` stays null for every card).
  - Not every "arena-card" is Basic rarity or excluded from packs: only
    the 3 young heroes' own dedicated weapon+arm-equipment are (matching
    plan S10); several other equipment pieces are Common or Legendary and
    are ordinary, draftable booster contents. `object_type == "hero"` (not
    `is_arena_card`) is what must be excluded from every pack regardless of
    rarity - see fabdraft_core.packs.generator.
  - Which 20 of the 40 Majestics are "expansion slot" (S13) isn't tagged
    directly, but the real data reveals a clean, unambiguous signal: the
    20 expansion Majestics occupy an exactly-contiguous block at the very
    end of the set's numbering (set_number 243-262 inclusive; every other
    card in the set is numbered 0-242). See `_EXPANSION_SLOT_THRESHOLD`.
  - The real rarity_counts (fabled 2, basic 14, majestic 40, rare 66,
    common 133, legendary 4, marvel 3 = 262 total) resolve the S3/S4
    mismatch escalated in docs/status/BLOCKED.md: the plan's own S4 table
    substantially overstated Marvel (27 vs the real 3) and Basic (16 vs
    14), and slightly overstated Legendary (5 vs 4).

Usage:
    uv run python scripts/ingest_cardvault.py --in-dir data/IAR \\
        --out data/sets/IAR.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from fabdraft_core.contracts import Card, SetSnapshot
from fabdraft_core.errors import DataIncompleteError

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ingest_set import default_draftable, load_expected_counts  # noqa: E402

# Confirmed 2026-09-14 against data/IAR/manifest.json's rarity_counts.
RARITY_WORD_MAP: dict[str, str] = {
    "common": "C",
    "rare": "R",
    "majestic": "M",
    "legendary": "L",
    "marvel": "V",
    "fabled": "F",
    "basic": "B",
}

OBJECT_TYPE_MAP: dict[str, str] = {
    "deck-card": "deck",
    "arena-card": "arena",
    "hero-card": "hero",
    "token": "token",
}

_EQUIPMENT_SLOTS = {"Head", "Chest", "Arms", "Legs"}

# See module docstring: the 20 expansion-slot Majestics are exactly
# set_number 243-262 in the real IAR export; every other card is 0-242.
_EXPANSION_SLOT_THRESHOLD = 243

# Hero name appears immediately before the word "Specialization" in Card
# Vault's text (e.g. "Legendary Viserai Specialization", "Viserai
# Specialization") - a different phrasing than the-fab-cube's
# "Specialization: Name." convention in scripts/ingest_set.py.
_SPECIALIZATION_RE = re.compile(r"(?:Legendary\s+)?([A-Z][A-Za-z']*)\s+Specialization")

# Card Vault's face schema has no dedicated keywords field (unlike
# the-fab-cube's card_keywords/ability_and_effect_keywords). There is no
# reliable general signal to extract *arbitrary* keywords from `text`
# without risking false positives, so this stays a small, explicit
# allow-list of keywords the plan itself already names (section 5.12) -
# never a blanket "any bolded term" scrape. Documented as incomplete.
_KNOWN_KEYWORDS = ("Blood Debt", "Go Again", "Dominate", "Usurp")

# plan S2: IAR releases 2026-09-25.
IAR_RELEASE_DATE = "2026-09-25"


def derive_cardvault_specialization(text: str) -> str | None:
    match = _SPECIALIZATION_RE.search(text)
    if match:
        return match.group(1)
    return None


def derive_cardvault_keywords(text: str) -> list[str]:
    return sorted(k for k in _KNOWN_KEYWORDS if k in text)


def parse_numeric(value: Any) -> int | None:
    """cost/power are usually already an int or null, but real IAR data
    confirms at least one card each with a variable value ("X" cost,
    "*" power) - a known contract gap (Card.cost/power can't represent
    "variable"), so this parses what it can and returns None rather than
    raising, same policy as scripts/ingest_set.py's parse_int.
    """
    if value is None or isinstance(value, int):
        return value
    return None


def derive_equipment_from_subtypes(subtypes: list[str]) -> tuple[str | None, int | None]:
    equipment_slot = next((s.lower() for s in subtypes if s in _EQUIPMENT_SLOTS), None)
    hands = 2 if "(2H)" in subtypes else (1 if "(1H)" in subtypes else None)
    return equipment_slot, hands


def find_default_printing(raw_card: dict[str, Any]) -> dict[str, Any]:
    default_id = raw_card.get("default_print_id")
    for printing in raw_card.get("printings") or []:
        if printing.get("print_id") == default_id:
            return printing  # type: ignore[no-any-return]
    raise DataIncompleteError(
        f"card {raw_card.get('card_id')!r}: no printing matches default_print_id {default_id!r}"
    )


def map_card(raw_card: dict[str, Any], set_code: str) -> Card:
    """Maps one Card Vault card entry (already unique per name+pitch) to
    our Card contract. Raises DataIncompleteError on anything missing or
    unmapped - never guesses.
    """
    card_id = raw_card.get("card_id")
    name = raw_card.get("name")
    if not card_id or not name:
        raise DataIncompleteError(f"card entry missing card_id/name: {raw_card!r}")

    faces = raw_card.get("faces") or []
    if not faces:
        raise DataIncompleteError(f"card {card_id!r} has no faces")
    face = faces[0]  # front face only - see module docstring re: DFC back faces

    rarity_word = raw_card.get("rarity")
    if rarity_word not in RARITY_WORD_MAP:
        raise DataIncompleteError(
            f"card {card_id!r} has unmapped rarity {rarity_word!r} - extend "
            "RARITY_WORD_MAP deliberately, do not guess."
        )
    rarity = RARITY_WORD_MAP[rarity_word]

    object_type_word = raw_card.get("object_type")
    if object_type_word not in OBJECT_TYPE_MAP:
        raise DataIncompleteError(
            f"card {card_id!r} has unmapped object_type {object_type_word!r} - extend "
            "OBJECT_TYPE_MAP deliberately, do not guess."
        )
    object_type = OBJECT_TYPE_MAP[object_type_word]

    default_printing = find_default_printing(raw_card)

    raw_classes = face.get("classes") or []
    classes = [] if raw_classes == ["Generic"] else raw_classes
    talents = face.get("talents") or []
    types = face.get("types") or []
    subtypes = face.get("subtypes") or []
    equipment_slot, hands = derive_equipment_from_subtypes(subtypes)

    functional_text = face.get("text") or ""
    specialization = derive_cardvault_specialization(functional_text)
    keywords = derive_cardvault_keywords(functional_text)

    is_expansion_slot = (
        rarity == "M" and default_printing.get("set_number", 0) >= _EXPANSION_SLOT_THRESHOLD
    )

    card_number = raw_card.get("default_print_id") or default_printing["print_id"]
    image_url = (face.get("image_urls") or {}).get("large")

    raw_cost, raw_power = face.get("cost"), face.get("power")
    has_unrepresentable_variable_value = any(
        isinstance(v, str) for v in (raw_cost, raw_power, face.get("defense"))
    )

    return Card(
        uid=card_id,
        set_code=set_code,
        card_number=card_number,
        name=name,
        pitch=face.get("pitch"),
        rarity=rarity,  # type: ignore[arg-type]
        types=types,
        classes=classes,
        talents=talents,
        subtypes=subtypes,
        cost=parse_numeric(face.get("cost")),
        power=parse_numeric(face.get("power")),
        defense=parse_numeric(face.get("defense")),
        life=parse_numeric(face.get("life")),
        intellect=parse_numeric(face.get("intellect")),
        keywords=keywords,
        functional_text=functional_text,
        specialization=specialization,
        object_type=object_type,  # type: ignore[arg-type]
        is_deck_card=object_type == "deck",
        is_arena_card=object_type == "arena",
        equipment_slot=equipment_slot,  # type: ignore[arg-type]
        hands=hands,  # type: ignore[arg-type]
        image_url=image_url,
        double_faced_with=None,  # see module docstring - intentionally unmodeled
        draftable=default_draftable(rarity, is_expansion_slot, object_type),
        is_expansion_slot=is_expansion_slot,
        data_complete=not has_unrepresentable_variable_value,
    )


def _product_name(raw_cards: list[dict[str, Any]]) -> str | None:
    for raw_card in raw_cards:
        for printing in raw_card.get("printings") or []:
            product = printing.get("product")
            if product:
                return str(product)
    return None


def build_snapshot(
    cards_payload: dict[str, Any],
    set_code: str,
    expected_counts: dict[str, int],
    *,
    provider: str = "cardvault.fabtcg.com",
    release_date: str = IAR_RELEASE_DATE,
) -> SetSnapshot:
    raw_cards = cards_payload.get("cards") or []
    if not raw_cards:
        raise DataIncompleteError("cards.json has no cards")

    cards = [map_card(raw_card, set_code) for raw_card in raw_cards]

    counts: dict[str, int] = {"total": len(cards)}
    for rarity in ("F", "V", "L", "M", "R", "C", "B"):
        counts[rarity] = sum(1 for c in cards if c.rarity == rarity)
    incomplete = [c.uid for c in cards if not c.data_complete]

    metadata = cards_payload.get("metadata") or {}
    retrieved_at = metadata.get("generated_at") or "1970-01-01T00:00:00Z"
    set_name = _product_name(raw_cards) or set_code

    return SetSnapshot(
        set_code=set_code,
        name=set_name,
        release_date=release_date,  # type: ignore[arg-type]
        source={  # type: ignore[arg-type]
            "provider": provider,
            "commit": f"export:{retrieved_at}",
            "retrieved_at": retrieved_at,
        },
        expected_counts=expected_counts,  # type: ignore[arg-type]
        cards=cards,
        integrity={  # type: ignore[arg-type]
            "counts_match": counts == expected_counts,
            "incomplete_cards": incomplete,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in-dir", type=Path, required=True, help="Directory containing cards.json"
    )
    parser.add_argument("--set-code", default=None, help="Defaults to cards.json's metadata")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    cards_payload = json.loads((args.in_dir / "cards.json").read_text())
    set_code = args.set_code or cards_payload.get("metadata", {}).get("set_code")
    if not set_code:
        raise DataIncompleteError("no --set-code given and cards.json has no metadata.set_code")

    expected_counts = load_expected_counts(set_code, config_dir=args.config_dir)
    snapshot = build_snapshot(cards_payload, set_code, expected_counts)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot.model_dump(mode="json", by_alias=True), indent=2))
    print(f"Wrote {len(snapshot.cards)} cards to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
