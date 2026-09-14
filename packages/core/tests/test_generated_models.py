"""Generated pydantic models (packages/core/fabdraft_core/contracts/generated,
built by scripts/generate_contract_models.py) must accept the same instances
the JSON Schemas accept, and reject extra fields the same way.
"""

from __future__ import annotations

import pytest
from fabdraft_core.contracts import Card, PickDecision
from pydantic import ValidationError


def test_card_model_round_trips_a_minimal_instance() -> None:
    data = {
        "uid": "FIXTURE001-1",
        "set_code": "FIXTURE",
        "card_number": "FIXTURE001",
        "name": "Fixture Card",
        "pitch": 1,
        "rarity": "C",
        "types": ["Action"],
        "classes": [],
        "talents": [],
        "subtypes": [],
        "cost": 1,
        "power": 2,
        "defense": None,
        "life": None,
        "intellect": None,
        "keywords": [],
        "functional_text": "",
        "specialization": None,
        "is_deck_card": True,
        "is_arena_card": False,
        "equipment_slot": None,
        "hands": None,
        "image_url": None,
        "double_faced_with": None,
        "draftable": True,
        "is_expansion_slot": False,
        "data_complete": True,
    }
    card = Card.model_validate(data)
    assert card.uid == "FIXTURE001-1"
    assert card.model_dump(mode="json") == data


def test_card_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Card.model_validate({"uid": "x", "unexpected_field": True})


def test_pick_decision_requires_only_picked_uid() -> None:
    decision = PickDecision.model_validate({"picked_uid": "FIXTURE001-1"})
    assert decision.picked_uid == "FIXTURE001-1"
    assert decision.reasoning is None
    assert decision.ranked_alternatives is None
