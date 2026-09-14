#!/usr/bin/env python3
"""Validate a SetSnapshot against its official rarity counts and per-card
completeness (plan section 2.5, WP-02).

Refuses (exit 1) to pass a set whose actual card counts don't match the
expected counts for its set_code (`data/config/{set_code}.expected_counts.json`,
never the snapshot's own self-reported `expected_counts`), or that has any
`data_complete=false` card - unless `--allow-incomplete` is given, in which
case it proceeds and stamps the result `data_integrity: incomplete`.

Usage:
    uv run python scripts/validate_set.py --in data/fixtures/fixture_set.json
    uv run python scripts/validate_set.py --in data/sets/IAR.json \\
        --allow-incomplete --out data/sets/IAR.validated.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fabdraft_core.cards.integrity import check_snapshot, enforce_gate
from fabdraft_core.contracts import SetSnapshot
from fabdraft_core.errors import DataIncompleteError

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    # Makes `from scripts.ingest_set import ...` work whether this file is
    # run directly (`python scripts/validate_set.py`, where only scripts/
    # itself lands on sys.path) or imported under pytest (where
    # pythonpath=["."] already covers this).
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ingest_set import load_expected_counts  # noqa: E402


def validate(
    snapshot: SetSnapshot, expected_counts: dict[str, int], *, allow_incomplete: bool
) -> tuple[SetSnapshot, str]:
    """Returns (snapshot with a freshly recomputed `integrity` field,
    data_integrity status). Raises DataIncompleteError if the gate refuses
    and `allow_incomplete` is False.
    """
    report = check_snapshot(snapshot, expected_counts)
    enforce_gate(report, allow_incomplete=allow_incomplete)
    integrity_cls = type(snapshot.integrity)
    stamped = snapshot.model_copy(
        update={
            "integrity": integrity_cls(
                counts_match=report.counts_match,
                incomplete_cards=report.incomplete_card_uids,
            )
        }
    )
    return stamped, report.data_integrity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", type=Path, required=True)
    parser.add_argument("--out", dest="out_path", type=Path, default=None)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Override the data/config directory expected_counts are read from (mainly for tests)",
    )
    args = parser.parse_args(argv)

    snapshot = SetSnapshot.model_validate(json.loads(args.in_path.read_text()))
    expected_counts = load_expected_counts(snapshot.set_code, config_dir=args.config_dir)

    try:
        stamped, status = validate(
            snapshot, expected_counts, allow_incomplete=args.allow_incomplete
        )
    except DataIncompleteError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    print(
        f"OK ({status}): {snapshot.set_code} - {len(snapshot.cards)} cards, data_integrity={status}"
    )
    if status == "incomplete":
        print(
            "WARNING: data_integrity=incomplete - this must be stamped on every "
            "downstream export and log (plan section 2.5, 11).",
            file=sys.stderr,
        )

    if args.out_path:
        args.out_path.parent.mkdir(parents=True, exist_ok=True)
        args.out_path.write_text(
            json.dumps(stamped.model_dump(mode="json", by_alias=True), indent=2)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
