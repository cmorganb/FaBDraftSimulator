"""Tests for IAR-specific synergy tag matchers (WP-10, plan S12).

Every matcher gets a positive and a negative case (plan's own acceptance
criterion), using fictional card text shaped like the real patterns
documented in `fabdraft_core/deck/iar_tags.py` - never real LSS card text.
"""

from __future__ import annotations

from fabdraft_core.contracts import Card
from fabdraft_core.deck.iar_tags import (
    has_blood_debt,
    has_go_again,
    is_banished_zone_payoff,
    is_gate_generator,
    is_runechant_generator,
    is_usurp_enabler,
)


def _card(
    *,
    functional_text: str = "",
    keywords: list[str] | None = None,
) -> Card:
    return Card(
        uid="fixture-test-card-red",
        set_code="FIXTURE",
        card_number="FIXTURE001",
        name="Fixture Test Card",
        pitch=1,
        rarity="C",
        types=["Action"],
        classes=[],
        talents=[],
        subtypes=[],
        cost=1,
        power=2,
        defense=2,
        life=None,
        intellect=None,
        keywords=keywords or [],
        functional_text=functional_text,
        specialization=None,
        object_type="deck",
        is_deck_card=True,
        is_arena_card=False,
        equipment_slot=None,
        hands=None,
        image_url=None,
        double_faced_with=None,
        draftable=True,
        is_expansion_slot=False,
        data_complete=True,
    )


def test_has_blood_debt_positive_via_keywords_list() -> None:
    assert has_blood_debt(_card(keywords=["Blood Debt"])) is True


def test_has_blood_debt_positive_via_bolded_text() -> None:
    assert has_blood_debt(_card(functional_text="**Blood Debt** _(reminder text)_")) is True


def test_has_blood_debt_negative() -> None:
    assert has_blood_debt(_card(functional_text="This card has no relevant keyword.")) is False


def test_has_go_again_positive() -> None:
    assert has_go_again(_card(functional_text="Deal 2 damage. **Go Again**")) is True


def test_has_go_again_negative() -> None:
    assert has_go_again(_card(functional_text="Deal 2 damage.")) is False


def test_is_gate_generator_positive() -> None:
    text = "When this hits, create a Gate to i'Arathael token."
    assert is_gate_generator(_card(functional_text=text)) is True


def test_is_gate_generator_negative() -> None:
    text = "When this hits, deal 2 damage to the defending hero."
    assert is_gate_generator(_card(functional_text=text)) is False


def test_is_banished_zone_payoff_positive() -> None:
    text = "You may play this from your banished zone."
    assert is_banished_zone_payoff(_card(functional_text=text)) is True


def test_is_banished_zone_payoff_negative_plain_banish_effect() -> None:
    """A card that merely banishes something as a one-off effect/cost is
    not a banished-zone *payoff* - it never mentions playing *from* the
    banished zone.
    """
    text = "Banish a card from your hand."
    assert is_banished_zone_payoff(_card(functional_text=text)) is False


def test_is_banished_zone_payoff_negative_unrelated_banished_zone_mention() -> None:
    text = "Look at the top card of your banished zone."
    assert is_banished_zone_payoff(_card(functional_text=text)) is False


def test_is_usurp_enabler_positive_bolded_keyword() -> None:
    text = (
        "**Usurp** _(As an additional cost to play this, destroy a Runechant "
        "if able. If you do, this gets +2{p}.)_"
    )
    assert is_usurp_enabler(_card(functional_text=text)) is True


def test_is_usurp_enabler_positive_verb_form() -> None:
    text = "If you've usurped this turn, this costs 2 less to play."
    assert is_usurp_enabler(_card(functional_text=text)) is True


def test_is_usurp_enabler_negative_set_legality_reminder_text_is_not_the_keyword() -> None:
    """The real false-positive trap: every Basic-rarity card legal in this
    format carries boilerplate reminder text naming the *set*, not the
    keyord - this must never be tagged as a genuine Usurp enabler.
    """
    text = "(You may add this to your card-pool in Usurp the Shadow Throne limited formats.)"
    assert is_usurp_enabler(_card(functional_text=text)) is False


def test_is_usurp_enabler_negative_no_mention() -> None:
    assert is_usurp_enabler(_card(functional_text="Deal 2 damage.")) is False


def test_is_runechant_generator_positive() -> None:
    text = "When this is pitched, create a Runechant token."
    assert is_runechant_generator(_card(functional_text=text)) is True


def test_is_runechant_generator_positive_for_each_phrasing() -> None:
    text = "Turn up to 3 cards face-down, then create a Runechant token for each card turned."
    assert is_runechant_generator(_card(functional_text=text)) is True


def test_is_runechant_generator_negative_consumer_not_generator() -> None:
    """A card that *destroys*/*consumes* a Runechant is not itself a
    generator - this is the distinction plan S12 asks for.
    """
    text = "As an additional cost to play this, destroy a Runechant if able."
    assert is_runechant_generator(_card(functional_text=text)) is False


def test_is_runechant_generator_negative_no_mention() -> None:
    assert is_runechant_generator(_card(functional_text="Deal 2 damage.")) is False
