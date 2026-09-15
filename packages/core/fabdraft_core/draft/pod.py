"""Pod topology: seat numbering and pass direction (plan section 6.2, D4).

# TRP 8.2.1: pack 1 passes left, pack 2 right, pack 3 left.
"""

from __future__ import annotations

from typing import Literal

PassDirection = Literal["left", "right"]

# D4: round 1 left, round 2 right, round 3 left.
_ROUND_DIRECTIONS: dict[int, PassDirection] = {1: "left", 2: "right", 3: "left"}


def pass_direction(round_number: int) -> PassDirection:
    if round_number not in _ROUND_DIRECTIONS:
        raise ValueError(f"round_number must be 1, 2, or 3, got {round_number}")
    return _ROUND_DIRECTIONS[round_number]


def next_seat(seat: int, round_number: int, pod_size: int = 8) -> int:
    """The seat that receives `seat`'s pack next (plan section 6.2:
    "round 1 left (seat+1 mod 8), round 2 right (seat-1 mod 8), round 3
    left").
    """
    direction = pass_direction(round_number)
    if direction == "left":
        return (seat + 1) % pod_size
    return (seat - 1) % pod_size
