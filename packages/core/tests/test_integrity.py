"""Tests for the pure set-integrity checks (WP-02)."""

from __future__ import annotations

import pytest
from fabdraft_core.cards.integrity import (
    check_snapshot,
    enforce_gate,
    find_incomplete_card_uids,
    recompute_counts,
)
from fabdraft_core.contracts import Card, SetSnapshot
from fabdraft_core.errors import DataIncompleteError


def _card(uid: str, rarity: str, *, data_complete: bool = True) -> Card:
    return Card(
        uid=uid,
        set_code="MOCK",
        card_number=uid.upper(),
        name=uid,
        pitch=1,
        rarity=rarity,  # type: ignore[arg-type]
        types=["Action"],
        classes=[],
        talents=[],
        subtypes=[],
        cost=1,
        power=2,
        defense=2,
        life=None,
        intellect=None,
        keywords=[],
        functional_text="",
        specialization=None,
        is_deck_card=True,
        is_arena_card=False,
        equipment_slot=None,
        hands=None,
        image_url=None,
        double_faced_with=None,
        draftable=True,
        is_expansion_slot=False,
        data_complete=data_complete,
    )


def _snapshot(cards: list[Card], expected_counts: dict[str, int]) -> SetSnapshot:
    return SetSnapshot(
        set_code="MOCK",
        name="Mock",
        release_date="2026-01-01",  # type: ignore[arg-type]
        source={  # type: ignore[arg-type]
            "provider": "test",
            "commit": "n/a",
            "retrieved_at": "2026-01-01T00:00:00Z",
        },
        expected_counts=expected_counts,  # type: ignore[arg-type]
        cards=cards,
        integrity={"counts_match": True, "incomplete_cards": []},  # type: ignore[arg-type]
    )


def test_recompute_counts_tallies_by_rarity() -> None:
    cards = [_card("a", "C"), _card("b", "C"), _card("c", "R")]
    counts = recompute_counts(cards)
    assert counts == {"total": 3, "F": 0, "V": 0, "L": 0, "M": 0, "R": 1, "C": 2, "B": 0}


def test_find_incomplete_card_uids() -> None:
    cards = [_card("a", "C"), _card("b", "C", data_complete=False)]
    assert find_incomplete_card_uids(cards) == ["b"]


def test_check_snapshot_reports_match_when_actual_equals_expected() -> None:
    cards = [_card("a", "C"), _card("b", "R")]
    expected = {"total": 2, "F": 0, "V": 0, "L": 0, "M": 0, "R": 1, "C": 1, "B": 0}
    snapshot = _snapshot(cards, expected)
    report = check_snapshot(snapshot, expected)
    assert report.counts_match is True
    assert report.mismatches == {}
    assert report.incomplete_card_uids == []
    assert report.is_fully_valid is True
    assert report.data_integrity == "complete"


def test_check_snapshot_never_trusts_the_snapshots_own_expected_counts() -> None:
    """The gate's whole point is to catch a snapshot lying about its own
    counts - check_snapshot must compare against the caller-supplied
    authoritative expected_counts, not snapshot.expected_counts.
    """
    cards = [_card("a", "C")]
    # snapshot claims (falsely) that it matches a 5-common set
    lying_expected = {"total": 5, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 5, "B": 0}
    snapshot = _snapshot(cards, lying_expected)

    real_expected = {"total": 1, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 1, "B": 0}
    report = check_snapshot(snapshot, real_expected)
    assert report.counts_match is True  # matches the *real* expectation, not the lie

    report_against_lie = check_snapshot(snapshot, lying_expected)
    assert report_against_lie.counts_match is False


def test_check_snapshot_reports_mismatches_with_actual_and_expected_values() -> None:
    cards = [_card("a", "C"), _card("b", "C")]
    expected = {"total": 3, "F": 0, "V": 0, "L": 0, "M": 0, "R": 1, "C": 2, "B": 0}
    snapshot = _snapshot(cards, expected)
    report = check_snapshot(snapshot, expected)
    assert report.counts_match is False
    assert report.mismatches == {"R": (0, 1), "total": (2, 3)}
    assert report.is_fully_valid is False
    assert report.data_integrity == "incomplete"


def test_enforce_gate_passes_silently_when_fully_valid() -> None:
    cards = [_card("a", "C")]
    expected = {"total": 1, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 1, "B": 0}
    snapshot = _snapshot(cards, expected)
    report = check_snapshot(snapshot, expected)
    enforce_gate(report, allow_incomplete=False)  # must not raise


def test_enforce_gate_raises_on_count_mismatch_without_allow_incomplete() -> None:
    cards = [_card("a", "C")]
    expected = {"total": 2, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 2, "B": 0}
    snapshot = _snapshot(cards, expected)
    report = check_snapshot(snapshot, expected)
    with pytest.raises(DataIncompleteError, match="count mismatch"):
        enforce_gate(report, allow_incomplete=False)


def test_enforce_gate_raises_on_incomplete_cards_without_allow_incomplete() -> None:
    cards = [_card("a", "C", data_complete=False)]
    expected = {"total": 1, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 1, "B": 0}
    snapshot = _snapshot(cards, expected)
    report = check_snapshot(snapshot, expected)
    with pytest.raises(DataIncompleteError, match="incomplete card"):
        enforce_gate(report, allow_incomplete=False)


def test_enforce_gate_does_not_raise_when_allow_incomplete_even_if_invalid() -> None:
    cards = [_card("a", "C", data_complete=False)]
    expected = {"total": 99, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 99, "B": 0}
    snapshot = _snapshot(cards, expected)
    report = check_snapshot(snapshot, expected)
    enforce_gate(report, allow_incomplete=True)  # must not raise
    assert report.data_integrity == "incomplete"
