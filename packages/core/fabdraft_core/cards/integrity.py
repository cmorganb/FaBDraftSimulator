"""Set integrity checks (plan section 2.5, WP-02): does an ingested/generated
SetSnapshot's card list actually match the counts it claims, and is every
card fully specified?

Pure and I/O-free (plan section 4.1 item 2) - callers own reading the
authoritative expected-counts config and deciding what to do with the
result (`scripts/validate_set.py` is the CLI gate that does that I/O).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from fabdraft_core.contracts import Card, SetSnapshot
from fabdraft_core.errors import DataIncompleteError

RARITIES: tuple[str, ...] = ("F", "V", "L", "M", "R", "C", "B")


def recompute_counts(cards: list[Card]) -> dict[str, int]:
    """Actual per-rarity counts, derived directly from the card list - never
    trusted from a snapshot's own self-reported `expected_counts`.
    """
    counts: dict[str, int] = {"total": len(cards)}
    for rarity in RARITIES:
        counts[rarity] = sum(1 for c in cards if c.rarity == rarity)
    return counts


def find_incomplete_card_uids(cards: list[Card]) -> list[str]:
    return [c.uid for c in cards if not c.data_complete]


@dataclass(frozen=True)
class IntegrityReport:
    actual_counts: dict[str, int]
    expected_counts: dict[str, int]
    incomplete_card_uids: list[str] = field(default_factory=list)

    @property
    def counts_match(self) -> bool:
        return self.actual_counts == self.expected_counts

    @property
    def mismatches(self) -> dict[str, tuple[int, int]]:
        """{key: (actual, expected)} for every key that disagrees."""
        keys = set(self.actual_counts) | set(self.expected_counts)
        return {
            k: (self.actual_counts.get(k, 0), self.expected_counts.get(k, 0))
            for k in sorted(keys)
            if self.actual_counts.get(k, 0) != self.expected_counts.get(k, 0)
        }

    @property
    def is_fully_valid(self) -> bool:
        return self.counts_match and not self.incomplete_card_uids

    @property
    def data_integrity(self) -> str:
        return "complete" if self.is_fully_valid else "incomplete"


def check_snapshot(snapshot: SetSnapshot, expected_counts: Mapping[str, int]) -> IntegrityReport:
    """Recomputes counts and incomplete-card list from `snapshot.cards` and
    compares against `expected_counts` - the authoritative source (e.g. from
    `data/config/{set_code}.expected_counts.json`), NOT
    `snapshot.expected_counts` (which is just whatever the ingestion step
    happened to embed, and is exactly what a validation gate exists to
    double-check).
    """
    return IntegrityReport(
        actual_counts=recompute_counts(snapshot.cards),
        expected_counts=dict(expected_counts),
        incomplete_card_uids=find_incomplete_card_uids(snapshot.cards),
    )


def enforce_gate(report: IntegrityReport, *, allow_incomplete: bool) -> None:
    """Raises DataIncompleteError when the set fails the gate, unless
    `allow_incomplete` is set (plan section 2.5: "a hard validation gate
    refuses to load a set unless counts match ... or the operator explicitly
    passes --allow-incomplete").
    """
    if report.is_fully_valid or allow_incomplete:
        return
    reasons: list[str] = []
    if not report.counts_match:
        reasons.append(f"rarity count mismatch (actual vs expected): {report.mismatches}")
    if report.incomplete_card_uids:
        reasons.append(
            f"{len(report.incomplete_card_uids)} incomplete card(s), e.g. "
            f"{report.incomplete_card_uids[:5]}"
        )
    raise DataIncompleteError(
        "; ".join(reasons) + " - pass --allow-incomplete to load anyway (stamps "
        "data_integrity: incomplete)"
    )
