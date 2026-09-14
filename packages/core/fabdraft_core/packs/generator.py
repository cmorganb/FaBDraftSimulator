"""Booster pack generation (plan section 6.1, WP-05).

Pure and deterministic: given a card pool, a PackConfig, and an already-
derived SeededRng, always produces the same Pack. Callers derive the rng as
`rng_for(seed, "pack", round, pack_index)` (plan section 6.1) - this module
never touches the seed or randomness source directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from fabdraft_core.contracts import Card, PackConfig
from fabdraft_core.contracts.generated.pack_config_schema import Slot
from fabdraft_core.errors import PackGenerationError
from fabdraft_core.rng import SeededRng

# Rarity codes that are drawn straight from Card.rarity. "M_expansion" and
# "CF" (used by the chase slot, plan section 5.4) are pseudo-keys handled
# specially in _pool_for_rarity_key - they don't correspond to a Card.rarity
# value on their own.
_PLAIN_RARITIES = {"C", "R", "M", "L", "V", "F", "B"}


@dataclass(frozen=True)
class PackedCard:
    """One card as it appears in a specific drafted pack instance. A card's
    draftability here is a property of the *slot* it came from (plan
    section 6.1's `instance(card, ..., draftable=slot.draftable)`), not
    necessarily the same as `Card.draftable`'s static default.
    """

    card: Card
    slot_id: str
    foiling: str | None
    draftable: bool


@dataclass(frozen=True)
class Pack:
    """A generated pack, cards in physical pack order (plan section 6.1:
    "preserve order in the log so pack contents are reproducible").
    """

    cards: list[PackedCard]

    @property
    def draftable_cards(self) -> list[PackedCard]:
        return [c for c in self.cards if c.draftable]


def index_by_rarity(cards: list[Card]) -> dict[str, list[Card]]:
    """Indexes deck-legal cards (excluding heroes/weapons/equipment - plan
    section 6.1: "excluding heroes/tokens per format config") by rarity.
    """
    index: dict[str, list[Card]] = {}
    for card in cards:
        if not card.is_deck_card:
            continue
        index.setdefault(card.rarity, []).append(card)
    return index


def slot_weights(slot: Slot) -> dict[str, float]:
    return {key: weight.root for key, weight in slot.rarities.items()}


def _pool_for_rarity_key(
    rarity_key: str,
    *,
    pool_by_rarity: dict[str, list[Card]],
    all_deck_cards: list[Card],
    slot: Slot,
) -> list[Card]:
    """Candidate cards for one weighted-choice draw within a slot. Handles
    the chase slot's pseudo-rarity-keys (plan section 5.4) and enforces S13
    (expansion-slot Majestics never eligible for a draftable slot).
    """
    if rarity_key == "M_expansion":
        return [c for c in pool_by_rarity.get("M", []) if c.is_expansion_slot]
    if rarity_key == "CF":
        # Cold foil (plan S8/S14): a foiled instance of any card in the set.
        # This slot's whole distribution is already flagged `confidence:
        # ESTIMATED` in pack_config - this is a deliberate simplification,
        # not a guess at unavailable data.
        return all_deck_cards
    if rarity_key not in _PLAIN_RARITIES:
        raise PackGenerationError(
            f"slot {slot.id!r}: unrecognized rarity key {rarity_key!r} in its "
            "rarities config - extend _PLAIN_RARITIES or _pool_for_rarity_key "
            "deliberately, do not guess."
        )

    pool = pool_by_rarity.get(rarity_key, [])
    if rarity_key == "M":
        # S13: expansion-slot Majestics must never appear in a draftable
        # slot. A non-draftable slot with an explicit majestic_subset of
        # "expansion" is allowed to want them; everything else (including a
        # draftable slot with no explicit majestic_subset, e.g. rainbow
        # foil) defaults to core-only.
        if slot.majestic_subset == "expansion":
            pool = [c for c in pool if c.is_expansion_slot]
        elif slot.majestic_subset == "core" or slot.draftable:
            pool = [c for c in pool if not c.is_expansion_slot]
    return pool


def generate_pack(cards: list[Card], pack_config: PackConfig, rng: SeededRng) -> Pack:
    """plan section 6.1's `generate_pack(set, pack_config, rng) -> Pack`.
    `cards` is a set snapshot's full card list (e.g. `snapshot.cards`).
    """
    pool_by_rarity = index_by_rarity(cards)
    all_deck_cards = [c for c in cards if c.is_deck_card]
    picked: list[PackedCard] = []
    picked_uids: set[str] = set()

    for slot in pack_config.slots:
        weights = slot_weights(slot)
        for _ in range(slot.count):
            rarity_key = rng.weighted_choice(weights)
            candidates = _pool_for_rarity_key(
                rarity_key,
                pool_by_rarity=pool_by_rarity,
                all_deck_cards=all_deck_cards,
                slot=slot,
            )
            if pack_config.no_duplicate_uids_within_pack:
                candidates = [c for c in candidates if c.uid not in picked_uids]
            if not candidates:
                raise PackGenerationError(
                    f"slot {slot.id!r}: no candidates left for rarity key "
                    f"{rarity_key!r} (majestic_subset={slot.majestic_subset!r})"
                )
            card = rng.choice(candidates)
            picked.append(
                PackedCard(
                    card=card, slot_id=slot.id, foiling=slot.foiling, draftable=slot.draftable
                )
            )
            if pack_config.no_duplicate_uids_within_pack:
                picked_uids.add(card.uid)

    if len(picked) != pack_config.pack_size:
        raise PackGenerationError(
            f"generated {len(picked)} cards but pack_config.pack_size={pack_config.pack_size}"
        )
    return Pack(cards=picked)
