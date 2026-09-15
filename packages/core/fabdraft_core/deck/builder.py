"""Deck build + validation (plan section 6.3, WP-09).

Two pure pieces:
  - `legal_pool`: a seat's full legal card-pool (plan L1: drafted cards plus
    any number of Basic-rarity cards from the set - "a Player does not have
    to open the basic-rarity cards to use them"). A hero's own dedicated
    basic weapon/arm-equipment (plan S10) needs no special-casing: it is
    already Basic rarity, so it is already in this pool, and
    `card_playable_by` (class/talent subset, WP-06) is what naturally keeps
    e.g. Levia from actually using Malice's Necromancer-restricted basic
    weapon. Pool membership and per-hero legality are deliberately kept
    separate, composable checks.
  - `validate_deck`: checks a proposed hero + arena-card + deck-card
    selection against that pool, returning every reachable violation code
    from `contracts/decklist.schema.json`'s `Violation.code` enum.

# CR 1.3.2: "There are 4 categories of cards: hero-, token-, deck-, and
# arena-cards." A hero is its own category - CR 1.1.3 defines a player's
# *card-pool* as "a collection of deck-cards and arena-cards" only, which is
# why hero selection is validated separately (NO_HERO / HERO_NOT_YOUNG)
# rather than via pool membership.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from fabdraft_core.cards.legality import FormatRules, card_playable_by
from fabdraft_core.contracts import Card

ViolationCode = Literal[
    "DECK_SIZE",
    "ILLEGAL_CARD",
    "NOT_IN_POOL",
    "NO_HERO",
    "HERO_NOT_YOUNG",
    "EQUIP_SLOT_CONFLICT",
    "WEAPON_HANDS",
    "ARENA_CARD_IN_DECK",
    "FORMAT_RESTRICTION",
]

# CR 3.0.2: "Each player has... two weapon zones."
WEAPON_ZONES = 2

# CR 4.1.4a: "A player may select up to one arena-card for each of their
# arms, chest, head, legs, and weapon zones."
_EQUIPMENT_SLOTS_MAX_ONE_EACH = ("head", "chest", "arms", "legs")

DEFAULT_DECK_SIZE = 30  # plan L5, TRP 8.2


@dataclass(frozen=True)
class Violation:
    code: ViolationCode
    message: str


@dataclass(frozen=True)
class ValidationResult:
    violations: tuple[Violation, ...] = field(default_factory=tuple)

    @property
    def valid(self) -> bool:
        return len(self.violations) == 0


def legal_pool(drafted_cards: list[Card], all_set_cards: list[Card]) -> list[Card]:
    """plan L1: the drafted cards, plus any Basic-rarity card from the set
    that wasn't already drafted (avoids double-listing a Basic card that
    happened to be drafted anyway).
    """
    drafted_uids = {c.uid for c in drafted_cards}
    basics = [c for c in all_set_cards if c.rarity == "B" and c.uid not in drafted_uids]
    return [*drafted_cards, *basics]


def _check_pool_membership_and_legality(
    card: Card,
    *,
    pool_uids: set[str],
    hero: Card | None,
    format_rules: FormatRules | None,
) -> list[Violation]:
    violations: list[Violation] = []
    if card.uid not in pool_uids:
        violations.append(Violation("NOT_IN_POOL", f"{card.uid} is not in the legal pool"))
        return violations  # legality is moot if it isn't even in the pool

    # TRP 8.2's "format-specific restrictions" (plan L7): a banned card is
    # a *format*-wide restriction, so it's checked independently of hero
    # selection (FORMAT_RESTRICTION), separately from class/talent/
    # Specialization legality (ILLEGAL_CARD, which needs a hero to check
    # against). The two can both fire for the same card - that's correct,
    # not double-counting: they're independent facts.
    rules = format_rules or FormatRules()
    if card.uid in rules.banned_in_limited:
        violations.append(Violation("FORMAT_RESTRICTION", f"{card.uid} is banned in this format"))

    # Pass no format_rules here: banned-ness is already reported above as
    # FORMAT_RESTRICTION - card_playable_by's own banned-list check would
    # otherwise also report it as ILLEGAL_CARD, conflating a format-wide
    # restriction with a hero-specific one.
    if hero is not None and not card_playable_by(card, hero):
        violations.append(Violation("ILLEGAL_CARD", f"{card.uid} is not playable by {hero.name}"))
    return violations


def validate_deck(
    *,
    pool: list[Card],
    hero: Card | None,
    arena_cards: list[Card],
    deck_cards: list[Card],
    deck_size: int = DEFAULT_DECK_SIZE,
    format_rules: FormatRules | None = None,
) -> ValidationResult:
    """Validates a proposed deck registration. `hero`, when not None, must
    be a Card with `object_type == "hero"` (raises ValueError otherwise,
    same convention as `card_playable_by` - a caller bug, not a legality
    question).
    """
    if hero is not None and hero.object_type != "hero":
        raise ValueError(f"validate_deck: hero must be object_type='hero', got {hero!r}")

    violations: list[Violation] = []
    pool_uids = {c.uid for c in pool}

    if hero is None:
        violations.append(Violation("NO_HERO", "no hero selected"))
    elif "Young" not in hero.subtypes:
        # confirmed against real IAR data: every young hero has "Young" in
        # subtypes (never in types); adult forms don't - plan section 8.2
        # "Players must play as a young hero from the set(s)".
        violations.append(Violation("HERO_NOT_YOUNG", f"{hero.name} is not a young hero"))

    if len(deck_cards) != deck_size:
        violations.append(
            Violation("DECK_SIZE", f"deck has {len(deck_cards)} cards, expected {deck_size}")
        )

    for card in deck_cards:
        # CR 1.3.2d / CR 4.1.5a: "An arena-card... cannot start the game in
        # a player's deck." Broadened to "must actually be a deck-card" so
        # a hero or token ending up here is caught the same way.
        if card.object_type != "deck":
            violations.append(
                Violation("ARENA_CARD_IN_DECK", f"{card.uid} is a {card.object_type} card")
            )
            continue
        violations.extend(
            _check_pool_membership_and_legality(
                card, pool_uids=pool_uids, hero=hero, format_rules=format_rules
            )
        )

    for card in arena_cards:
        violations.extend(
            _check_pool_membership_and_legality(
                card, pool_uids=pool_uids, hero=hero, format_rules=format_rules
            )
        )

    # CR 4.1.4a: at most one arena-card per body-equipment zone.
    slot_counts = Counter(
        c.equipment_slot for c in arena_cards if c.equipment_slot in _EQUIPMENT_SLOTS_MAX_ONE_EACH
    )
    for slot, count in sorted(slot_counts.items()):
        if count > 1:
            violations.append(
                Violation("EQUIP_SLOT_CONFLICT", f"{count} arena-cards assigned to the {slot} slot")
            )

    # CR 3.0.2 / 3.16.2a / 8.2.1b / 8.2.2b: two weapon zones total; a (1H)
    # weapon needs one, a (2H) weapon needs two.
    total_hands = sum(c.hands for c in arena_cards if c.hands is not None)
    if total_hands > WEAPON_ZONES:
        violations.append(
            Violation(
                "WEAPON_HANDS",
                f"selected weapons need {total_hands} weapon zones, only {WEAPON_ZONES} available",
            )
        )

    return ValidationResult(violations=tuple(violations))
