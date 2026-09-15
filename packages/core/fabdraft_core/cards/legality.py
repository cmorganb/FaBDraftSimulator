"""Card-pool legality: which cards a hero may include in their card-pool
(plan section 6.3, WP-06).

# TRP 8.2 (Booster Draft Format): "A Player's booster draft card-pool
# comprises 1 young hero card and all cards in their limited-pool, subject
# to the class and/or talents of their hero, keywords, and format-specific
# restrictions... subject to any meta-static abilities of the cards in the
# card-pool (e.g. Specialization, Essence, etc.)"

A hero is represented as a `Card` with `object_type == "hero"` (plan
glossary: "Arena card: Hero, weapon, or equipment" - heroes have the same
`classes`/`talents`/`name` fields as any other card, per WP-05's finding
that real card data treats heroes as one more row in the same table).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fabdraft_core.contracts import Card


@dataclass(frozen=True)
class FormatRules:
    """The subset of a format's rules (plan section 5.3's `*.format.json`,
    not a formal contract - WP-09 owns loading that file) that legality
    needs. `Essence`-style exceptions that grant additional legal
    supertypes are a known gap - see docs/status/WP-06.md.
    """

    banned_in_limited: frozenset[str] = field(default_factory=frozenset)


_DEFAULT_FORMAT_RULES = FormatRules()


def moniker_of(name: str) -> str:
    """CR 2.7.3: a personal name's moniker is "the most significant
    identifier of the object's name" - e.g. "Viserai" for both
    "Viserai, Between Worlds" and "Viserai, the Forsaken" (CR 2.7.3,
    example). This project's hero names never use an honorific prefix (the
    CR's own "Ser Boltyn" -> "Boltyn" example would need one), so "the text
    before the first comma" is exact for every IAR hero this simulator
    handles; a name that did use an honorific would need a curated
    honorifics list to strip it, which IAR does not require.
    """
    return name.split(",")[0].strip()


def card_playable_by(card: Card, hero: Card, format_rules: FormatRules | None = None) -> bool:
    """True if `card` may be included in `hero`'s card-pool.

    `hero` must be a Card with `object_type == "hero"` - raises ValueError
    otherwise, since calling this with anything else is a caller bug, not a
    legality question.
    """
    if hero.object_type != "hero":
        raise ValueError(f"card_playable_by: hero must be object_type='hero', got {hero!r}")
    rules = format_rules or _DEFAULT_FORMAT_RULES

    # CR 1.1.3: "A card can only be included in a player's card-pool if the
    # card's supertypes are a subset of their hero's supertypes." CR 2.11.6:
    # "A supertype is either a class or a talent." An empty classes/talents
    # list (CR 2.14.1a: "Generic") is a subset of anything, including
    # itself - this is why a Generic card is always includable and why a
    # hero with no talent (impossible for a real hero, but not assumed
    # here) would only accept classless/talentless cards.
    if not set(card.classes) <= set(hero.classes):
        return False
    if not set(card.talents) <= set(hero.talents):
        return False

    # CR 8.3.7: "Specialization is... written as '[HERO] Specialization'
    # which means 'You may only have this in your deck if your hero is
    # [HERO],' where HERO is the moniker of the player's hero card.[2.7.3]"
    if card.specialization and card.specialization != moniker_of(hero.name):
        return False

    # TRP 8.2's "format-specific restrictions."
    return card.uid not in rules.banned_in_limited
