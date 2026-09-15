"""Tests for pod topology (WP-07, plan D4)."""

from __future__ import annotations

import pytest
from fabdraft_core.draft.pod import next_seat, pass_direction


def test_pass_direction_is_left_right_left() -> None:
    assert pass_direction(1) == "left"
    assert pass_direction(2) == "right"
    assert pass_direction(3) == "left"


def test_pass_direction_rejects_invalid_round() -> None:
    with pytest.raises(ValueError, match="1, 2, or 3"):
        pass_direction(4)


def test_next_seat_left_is_seat_plus_one_mod_pod_size() -> None:
    assert next_seat(0, round_number=1, pod_size=8) == 1
    assert next_seat(7, round_number=1, pod_size=8) == 0


def test_next_seat_right_is_seat_minus_one_mod_pod_size() -> None:
    assert next_seat(0, round_number=2, pod_size=8) == 7
    assert next_seat(7, round_number=2, pod_size=8) == 6


def test_next_seat_round_3_is_left_again() -> None:
    assert next_seat(0, round_number=3, pod_size=8) == 1


def test_next_seat_is_a_bijection_over_the_pod() -> None:
    for round_number in (1, 2, 3):
        receivers = {next_seat(s, round_number, pod_size=8) for s in range(8)}
        assert receivers == set(range(8))
