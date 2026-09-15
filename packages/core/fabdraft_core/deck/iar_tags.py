"""IAR-specific synergy tags (plan S12, WP-10): keyword/text matchers over
`Card.functional_text` (and `Card.keywords` where already reliable),
identifying cards relevant to IAR's named mechanics. Each matcher is
deliberately narrow and documents its own false-positive/negative risk -
plan section 6.4: "derived by keyword and text matching over
`functional_text`; matchers live in `core/deck/iar_tags.py` with a test per
tag and a documented false-positive rate."

Real-data grounding (confirmed against a Card Vault export of IAR,
gitignored, never committed - see docs/status/WP-01.md/WP-05.md for how it
was obtained):
  - "Gate to i'Arathael" appears verbatim in 41 real cards' functional text
    as a token name (e.g. "Create a Gate to i'Arathael token."). Low
    false-positive risk: it is a specific proper noun.
  - "banished zone" (lowercase) appears in 78 real cards, in both genuine
    "payoff" phrasing ("You may play this from your banished zone.") and
    plain banish-effect phrasing that isn't really a payoff. See
    `is_banished_zone_payoff` for how this is narrowed.
  - "Usurp" is a real bolded keyword ("**Usurp** _(As an additional cost to
    play this, destroy a Runechant if able...)_") - but EVERY Basic-rarity
    card legal in this format also carries unrelated boilerplate reminder
    text containing the substring "Usurp" as part of the SET NAME:
    "(You may add this to your card-pool in Usurp the Shadow Throne limited
    formats.)". A naive `"usurp" in text.lower()` search would tag every
    Basic-rarity card. See `is_usurp_enabler` for how this is avoided.
  - "Runechant" is not a card type/subtype in the real data - it only
    appears in functional text as a token name, in patterns like "create a
    Runechant token" (generator) or "destroy a Runechant" (consumer/cost).
"""

from __future__ import annotations

import re

from fabdraft_core.contracts import Card

GO_AGAIN_KEYWORD = "Go Again"
BLOOD_DEBT_KEYWORD = "Blood Debt"


def _has_keyword_or_bolded_text(card: Card, keyword: str) -> bool:
    """Prefers the structured `Card.keywords` list (populated at ingestion,
    WP-01) when it already contains `keyword`; falls back to a bolded-text
    search (`"**{keyword}**"`) for a card whose `keywords` list happens to
    be incomplete. Known false-negative risk: a card that states the
    keyword only in unbolded reminder/flavor text, with neither form
    present, would be missed - not observed in real data checked so far.
    """
    if keyword in card.keywords:
        return True
    return f"**{keyword}**" in card.functional_text


def has_blood_debt(card: Card) -> bool:
    """plan S12: the Blood Debt keyword."""
    return _has_keyword_or_bolded_text(card, BLOOD_DEBT_KEYWORD)


def has_go_again(card: Card) -> bool:
    """plan section 6.4's "go again density" input."""
    return _has_keyword_or_bolded_text(card, GO_AGAIN_KEYWORD)


_GATE_PHRASE = "Gate to i'Arathael"


def is_gate_generator(card: Card) -> bool:
    """plan S12: a card that creates a Gate to i'Arathael token. Matches the
    literal proper-noun phrase (confirmed verbatim in 41 real cards) -
    negligible false-positive risk since nothing else in the game is named
    this; false-negative risk only if a future reprint/errata phrases it
    differently (not observed in the data checked).
    """
    return _GATE_PHRASE in card.functional_text


_BANISHED_ZONE_PAYOFF_PATTERN = re.compile(
    r"play\b[^.]{0,40}from\b[^.]{0,30}banished zone", re.IGNORECASE
)


def is_banished_zone_payoff(card: Card) -> bool:
    """plan S12: a card that rewards playing from / having access to the
    banished zone (e.g. "You may play this from your banished zone.") - NOT
    merely a card that banishes something as a one-off cost or effect (e.g.
    "Banish a card from your hand.").

    Documented imprecision: this looks for "play ... from ... banished
    zone" within roughly one clause (a proximity regex, not full parsing),
    which covers the real "play this/cards from your banished zone" phrasing
    while excluding plain banish-effect text that doesn't mention playing
    from the zone (e.g. "look at the top card of your banished zone",
    "banish a card from your hand"). It will still miss a genuine payoff
    phrased in some other way, and could in principle match an unrelated
    sentence that happens to contain all three words in this order within
    the window - no such case was found in the real data checked, but this
    is a text heuristic, not a semantic understanding of the card.
    """
    return bool(_BANISHED_ZONE_PAYOFF_PATTERN.search(card.functional_text))


# Deliberately NOT a bare substring search for "usurp": every Basic-rarity
# card legal in this format also carries unrelated set-legality reminder
# text ("...in Usurp the Shadow Throne limited formats.") that contains the
# same letters as part of the SET NAME, not the keyword. Matching only the
# bolded keyword form or the verb form avoids that trap entirely, since
# neither pattern appears in the reminder phrase.
_USURP_KEYWORD_PATTERN = re.compile(r"\*\*usurp\*\*|\busurped\b", re.IGNORECASE)


def is_usurp_enabler(card: Card) -> bool:
    """plan S12: the Usurp keyword mechanic ("seizing opponents'
    Runechants"). Matches the bolded keyword form ("**Usurp**") or the verb
    form ("usurped this turn") - see the module-level note above for why
    this isn't a plain substring search.
    """
    return bool(_USURP_KEYWORD_PATTERN.search(card.functional_text))


_RUNECHANT_GENERATOR_PATTERN = re.compile(
    r"creates?\s+(?:a|an|\d+)\s+Runechant tokens?", re.IGNORECASE
)


def is_runechant_generator(card: Card) -> bool:
    """plan S12: a card that creates a Runechant token (e.g. "create a
    Runechant token", "create a Runechant token for each..."). Deliberately
    narrower than a bare "Runechant" substring search: excludes cards that
    merely consume or reference an existing Runechant as a cost or
    condition (e.g. "destroy a Runechant if able", "for each Runechant you
    control") without themselves generating one. False-negative risk: a
    future card that creates a Runechant via different phrasing (e.g. "put
    a Runechant into play") would not match this pattern.
    """
    return bool(_RUNECHANT_GENERATOR_PATTERN.search(card.functional_text))
