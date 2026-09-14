"""Shared test infrastructure. Schema loading here is test-only I/O; the
shipped `fabdraft_core` package never reads contracts/ off disk at runtime
(plan section 4.1 item 2 - core performs no I/O except through injected
ports). A product-facing schema/validation utility is WP-02's
`core/cards/integrity.py`, not this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "contracts"


def load_schema(name: str) -> dict[str, Any]:
    """Load contracts/{name}.schema.json as a raw dict."""
    path = CONTRACTS_DIR / f"{name}.schema.json"
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def build_registry() -> Registry[Any]:
    """A referencing.Registry over every contracts/*.schema.json, keyed by
    both its bare filename (used by relative $refs like "card.schema.json")
    and its declared $id, so cross-file $ref resolution works uniformly.
    """
    resources: list[tuple[str, Resource[Any]]] = []
    for path in sorted(CONTRACTS_DIR.glob("*.schema.json")):
        contents = json.loads(path.read_text())
        resource = Resource.from_contents(contents)
        resources.append((path.name, resource))
        schema_id = contents.get("$id")
        if schema_id:
            resources.append((schema_id, resource))
    return Registry().with_resources(resources)


@pytest.fixture(scope="session")
def schema_registry() -> Registry[Any]:
    return build_registry()


@pytest.fixture(scope="session")
def contracts_dir() -> Path:
    return CONTRACTS_DIR
