"""Tests for the TRP A.3 timer table (WP-07)."""

from __future__ import annotations

import pytest
from fabdraft_core.draft.timers import REVIEW_WINDOW_SECONDS, timer_seconds_for_pack_size


@pytest.mark.parametrize(
    ("pack_size", "expected_seconds"),
    [
        (14, 50),
        (13, 50),
        (12, 50),
        (11, 40),
        (10, 40),
        (9, 30),
        (8, 30),
        (7, 20),
        (6, 20),
        (5, 10),
        (4, 10),
        (3, 5),
        (2, 5),
        (1, None),
    ],
)
def test_timer_table_matches_trp_a3(pack_size: int, expected_seconds: int | None) -> None:
    assert timer_seconds_for_pack_size(pack_size) == expected_seconds


def test_timer_table_rejects_zero_or_negative() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        timer_seconds_for_pack_size(0)


def test_timer_table_rejects_sizes_beyond_trp_a3() -> None:
    with pytest.raises(ValueError, match="no TRP A.3 timer"):
        timer_seconds_for_pack_size(16)


def test_review_window_is_one_minute() -> None:
    assert REVIEW_WINDOW_SECONDS == 60


def test_one_round_duration_matches_plan_section_2_2() -> None:
    """plan section 2.2's derived check: an IAR pod round (packs start at 14
    draftable cards) totals 360 seconds.
    """
    total = sum(timer_seconds_for_pack_size(n) or 0 for n in range(14, 0, -1))
    assert total == 360
