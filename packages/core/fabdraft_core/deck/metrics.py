"""Pool and deck metrics (plan section 6.4, WP-10): pure, descriptive
statistics over a card list, for the report and the deck-build assistant.

None of these are a rating: plan section 6.4's own words - "No metric is
presented as an authoritative rating. The UI labels them 'pool shape', not
'score'." Every function/field name here is deliberately descriptive
(counts, distributions, densities), never evaluative (no "score", "rating",
"grade", or similar).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from fabdraft_core.cards.legality import card_playable_by
from fabdraft_core.contracts import Card
from fabdraft_core.deck.iar_tags import (
    has_blood_debt,
    has_go_again,
    is_banished_zone_payoff,
    is_gate_generator,
    is_runechant_generator,
    is_usurp_enabler,
)

_EQUIPMENT_SLOTS = ("head", "chest", "arms", "legs")

# plan section 6.4: "arcane sources" - Card has no dedicated `arcane` field
# (the upstream schemas' arcane-cost concept isn't carried into our
# contract), so this is a best-effort text proxy, not a structural count.
# Documented as an approximation, same spirit as the IAR tag matchers.
_ARCANE_TEXT_MARKER = "arcane"


def hero_playable_counts(pool: list[Card], heroes: list[Card]) -> dict[str, int]:
    """plan section 6.4: "Playable count per candidate hero (drives the
    'which hero was your pool actually best for' panel)." Reuses
    `card_playable_by` (WP-06) - no class/talent logic duplicated here.
    Keyed by hero uid so callers can look up by whichever hero they mean
    even if two heroes happen to share a display name.
    """
    return {hero.uid: sum(1 for c in pool if card_playable_by(c, hero)) for hero in heroes}


def pitch_distribution(cards: list[Card]) -> dict[int, int]:
    """Counts of pitch 1/2/3 among `cards` with a pitch value (arena cards
    and other pitch-less cards are excluded, not counted as 0)."""
    return dict(Counter(c.pitch for c in cards if c.pitch is not None))


def cost_curve(cards: list[Card]) -> dict[int, int]:
    """Cost -> count, for cards with a defined (non-variable) cost."""
    return dict(Counter(c.cost for c in cards if c.cost is not None))


def is_attack_action(card: Card) -> bool:
    return "Attack" in card.types


def attack_action_count(cards: list[Card]) -> int:
    return sum(1 for c in cards if is_attack_action(c))


def average_power(cards: list[Card]) -> float | None:
    powers = [c.power for c in cards if c.power is not None]
    return sum(powers) / len(powers) if powers else None


@dataclass(frozen=True)
class DefenseProfile:
    defense_3_count: int
    average_defense: float | None
    blue_block_count: int


def defense_profile(cards: list[Card]) -> DefenseProfile:
    """`blue_block_count`: pitch-3 cards with a defined defense value - a
    deckbuilding heuristic (blue-pitch cards are conventionally kept back
    as defensive resources in Flesh and Blood), not a rules-defined term.
    Documented rather than assumed obvious.
    """
    defenses = [c.defense for c in cards if c.defense is not None]
    return DefenseProfile(
        defense_3_count=sum(1 for c in cards if c.defense == 3),
        average_defense=sum(defenses) / len(defenses) if defenses else None,
        blue_block_count=sum(1 for c in cards if c.pitch == 3 and c.defense is not None),
    )


def go_again_density(cards: list[Card]) -> float:
    """Fraction (0.0-1.0) of `cards` with the Go Again keyword. 0.0 for an
    empty list, not an error - there is no meaningful density of nothing.
    """
    if not cards:
        return 0.0
    return sum(1 for c in cards if has_go_again(c)) / len(cards)


def arcane_source_count(cards: list[Card]) -> int:
    """Best-effort text proxy - see module-level note. Counts cards whose
    functional text mentions "arcane" at all (e.g. arcane damage effects),
    which over-counts relative to a true "arcane resource/source" count a
    structural `arcane` field would give.
    """
    return sum(1 for c in cards if _ARCANE_TEXT_MARKER in c.functional_text.lower())


def equipment_coverage_by_slot(cards: list[Card]) -> dict[str, int]:
    """How many `cards` occupy each equipment body-slot (plan section 6.4's
    "equipment coverage by slot") - counts every card with that
    `equipment_slot`, regardless of rarity/draftability, so this reflects
    coverage in whatever `cards` the caller passes (pool or deck).
    """
    counts: Counter[str] = Counter(
        c.equipment_slot for c in cards if c.equipment_slot in _EQUIPMENT_SLOTS
    )
    return {slot: counts.get(slot, 0) for slot in _EQUIPMENT_SLOTS}


def iar_tag_counts(cards: list[Card]) -> dict[str, int]:
    """plan S12's IAR-specific synergy tags (`fabdraft_core.deck.iar_tags`),
    aggregated into counts over `cards`.
    """
    return {
        "blood_debt": sum(1 for c in cards if has_blood_debt(c)),
        "gate_generators": sum(1 for c in cards if is_gate_generator(c)),
        "banished_zone_payoffs": sum(1 for c in cards if is_banished_zone_payoff(c)),
        "usurp_enablers": sum(1 for c in cards if is_usurp_enabler(c)),
        "runechant_generators": sum(1 for c in cards if is_runechant_generator(c)),
    }


@dataclass(frozen=True)
class PoolShape:
    """Descriptive "pool shape" statistics (plan section 6.4) over one card
    list - never an authoritative rating (see module docstring). Build with
    `compute_pool_shape`.
    """

    card_count: int
    hero_playable_counts: dict[str, int] = field(default_factory=dict)
    pitch_distribution: dict[int, int] = field(default_factory=dict)
    cost_curve: dict[int, int] = field(default_factory=dict)
    attack_action_count: int = 0
    average_power: float | None = None
    defense_profile: DefenseProfile = field(default_factory=lambda: DefenseProfile(0, None, 0))
    go_again_density: float = 0.0
    arcane_source_count: int = 0
    equipment_coverage_by_slot: dict[str, int] = field(default_factory=dict)
    iar_tag_counts: dict[str, int] = field(default_factory=dict)


def compute_pool_shape(cards: list[Card], heroes: list[Card] | None = None) -> PoolShape:
    """Computes every metric above over `cards` (pass a seat's drafted pool,
    or a proposed 30-card deck, or any other subset the caller wants shape
    statistics for). `heroes`, when given, populates `hero_playable_counts`;
    omit it (or pass `[]`) when there's no candidate-hero comparison to make.
    """
    return PoolShape(
        card_count=len(cards),
        hero_playable_counts=hero_playable_counts(cards, heroes or []),
        pitch_distribution=pitch_distribution(cards),
        cost_curve=cost_curve(cards),
        attack_action_count=attack_action_count(cards),
        average_power=average_power(cards),
        defense_profile=defense_profile(cards),
        go_again_density=go_again_density(cards),
        arcane_source_count=arcane_source_count(cards),
        equipment_coverage_by_slot=equipment_coverage_by_slot(cards),
        iar_tag_counts=iar_tag_counts(cards),
    )
