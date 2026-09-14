"""Contract tests for contracts/*.schema.json (WP-03).

These validate the schemas themselves (well-formed, $refs resolve) and, per
plan section 5.6, that AgentView cannot structurally carry another seat's
identity, pool, or pick.
"""

from __future__ import annotations

from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry

from .conftest import CONTRACTS_DIR, load_schema

ALL_SCHEMA_NAMES = sorted(
    p.stem.removesuffix(".schema") for p in CONTRACTS_DIR.glob("*.schema.json")
)


def test_discovered_all_eight_contracts() -> None:
    assert ALL_SCHEMA_NAMES == [
        "agent_view",
        "card",
        "decklist",
        "draft_event",
        "pack_config",
        "pick_decision",
        "session_config",
        "set",
    ]


def test_every_schema_is_well_formed_draft_2020_12(schema_registry: Registry[Any]) -> None:
    for name in ALL_SCHEMA_NAMES:
        schema = load_schema(name)
        Draft202012Validator.check_schema(schema)


def _minimal_card(uid: str = "FIXTURE001-1") -> dict[str, Any]:
    return {
        "uid": uid,
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


def test_a_minimal_card_validates(schema_registry: Registry[Any]) -> None:
    validator = Draft202012Validator(load_schema("card"), registry=schema_registry)
    validator.validate(_minimal_card())


def test_set_schema_cross_file_ref_resolves_against_a_real_card(
    schema_registry: Registry[Any],
) -> None:
    schema = load_schema("set")
    assert schema["properties"]["cards"]["items"]["$ref"] == "card.schema.json"
    validator = Draft202012Validator(schema, registry=schema_registry)
    minimal_set: dict[str, Any] = {
        "set_code": "FIXTURE",
        "name": "Fixture Set",
        "release_date": "2026-01-01",
        "source": {
            "provider": "synthetic",
            "commit": "n/a",
            "retrieved_at": "2026-01-01T00:00:00Z",
        },
        "expected_counts": {
            "total": 1,
            "F": 0,
            "V": 0,
            "L": 0,
            "M": 0,
            "R": 0,
            "C": 1,
            "B": 0,
        },
        "cards": [_minimal_card()],
        "integrity": {"counts_match": True, "incomplete_cards": []},
    }
    validator.validate(minimal_set)

    broken_card = _minimal_card()
    del broken_card["rarity"]
    minimal_set["cards"] = [broken_card]
    with pytest.raises(ValidationError):
        validator.validate(minimal_set)


# --- AgentView information-policy contract test (plan section 5.6) ---

_ALLOWED_TOP_LEVEL_AGENT_VIEW_FIELDS = {
    "schema_version",
    "seat",
    "pod_size",
    "round",
    "pick_number",
    "picks_remaining_in_round",
    "pass_direction",
    "time_limit_ms",
    "pack",
    "own_pool",
    "own_pool_visible",
    "memory",
    "format",
    "notes",
}

# Fields that would carry another seat's identity, pool, or pick if present
# anywhere in the schema. If a future schema edit introduces one of these,
# this test must fail loudly rather than let it slide through.
_FORBIDDEN_SUBSTRINGS = ("other_seat", "opponent", "other_pool", "other_pick", "all_seats", "seats")


def _walk_property_names(node: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for key, subschema in props.items():
                names.add(key)
                if isinstance(subschema, dict):
                    names |= _walk_property_names(subschema)
        items = node.get("items")
        if isinstance(items, dict):
            names |= _walk_property_names(items)
    return names


def test_agent_view_top_level_fields_match_allow_list() -> None:
    schema = load_schema("agent_view")
    assert schema["additionalProperties"] is False
    assert set(schema["properties"].keys()) == _ALLOWED_TOP_LEVEL_AGENT_VIEW_FIELDS


def test_agent_view_every_object_forbids_additional_properties() -> None:
    schema = load_schema("agent_view")

    def check(node: dict[str, Any]) -> None:
        if node.get("type") == "object":
            keys = node.get("properties", {}).keys()
            assert node.get("additionalProperties") is False, (
                f"object node without additionalProperties: false: {keys}"
            )
        for subschema in node.get("properties", {}).values():
            if isinstance(subschema, dict):
                check(subschema)
        items = node.get("items")
        if isinstance(items, dict):
            check(items)

    check(schema)


def test_agent_view_has_no_field_naming_another_seat() -> None:
    schema = load_schema("agent_view")
    names = _walk_property_names(schema)
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        matches = {n for n in names if forbidden in n.lower()}
        assert not matches, f"AgentView schema has a field suggesting other-seat info: {matches}"
