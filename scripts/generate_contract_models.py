#!/usr/bin/env python3
"""Regenerate pydantic models from contracts/*.schema.json (plan section 4.1 item 3:
contracts are the source of truth; no hand-written duplicates).

Usage:
    uv run python scripts/generate_contract_models.py

CI (see .github/workflows/ci.yml, "Regenerate contracts and diff-check") runs
this and then `git diff --exit-code` on the output directory, so a schema
change without regenerating fails the build (CI gate 7).

TypeScript codegen is not implemented here yet - this environment has no
working npm (see docs/decisions/ADR-0001-uv-workspace-and-deferred-web-tooling.md).
Add a TS generation step alongside this one once apps/web is scaffolded.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = REPO_ROOT / "contracts"
OUTPUT_DIR = REPO_ROOT / "packages" / "core" / "fabdraft_core" / "contracts" / "generated"

# Keep in sync with the schema filenames in contracts/. Each entry is
# (schema stem, generated module stem, exported class name) so
# contracts/__init__.py can re-export a stable, hand-written public API
# over the generated modules.
# Ordered by generated module name (matches ruff's import sort, so the
# written __init__.py never needs a --fix pass).
EXPORTS: list[tuple[str, str, str]] = [
    ("agent_view", "agent_view_schema", "AgentView"),
    ("card", "card_schema", "Card"),
    ("decklist", "decklist_schema", "Decklist"),
    ("draft_event", "draft_event_schema", "DraftEvent"),
    ("pack_config", "pack_config_schema", "PackConfig"),
    ("pick_decision", "pick_decision_schema", "PickDecision"),
    ("session_config", "session_config_schema", "SessionConfig"),
    ("set", "set_schema", "SetSnapshot"),
]


def run_codegen() -> None:
    if OUTPUT_DIR.exists():
        for f in OUTPUT_DIR.glob("*.py"):
            f.unlink()
    else:
        OUTPUT_DIR.mkdir(parents=True)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "datamodel_code_generator",
            "--input",
            str(CONTRACTS_DIR),
            "--input-file-type",
            "jsonschema",
            "--output",
            str(OUTPUT_DIR),
            "--output-model-type",
            "pydantic_v2.BaseModel",
            "--target-python-version",
            "3.12",
            "--use-schema-description",
            "--field-constraints",
            "--strict-nullable",
            "--no-allow-remote-refs",
            "--enum-field-as-literal",
            "all",
            "--use-standard-collections",
            "--use-union-operator",
            "--snake-case-field",
            "--formatters",
            "ruff-check",
            "ruff-format",
        ],
        cwd=REPO_ROOT,
        check=True,
    )


def write_public_init() -> None:
    lines = [
        '"""Generated pydantic models for contracts/*.schema.json.',
        "",
        "Do not hand-edit this file's imports - regenerate with",
        "scripts/generate_contract_models.py. Re-exports a stable name per",
        "contract so callers write `from fabdraft_core.contracts import Card`",
        "instead of reaching into `.generated.card_schema`.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
    ]
    for _, module, cls in EXPORTS:
        lines.append(f"from .generated.{module} import {cls} as {cls}")
    lines.append("")
    lines.append("__all__ = [")
    for _, _, cls in EXPORTS:
        lines.append(f'    "{cls}",')
    lines.append("]")
    lines.append("")

    init_path = OUTPUT_DIR.parent / "__init__.py"
    init_path.write_text("\n".join(lines))


def main() -> None:
    run_codegen()
    write_public_init()
    print(f"Wrote generated models to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
