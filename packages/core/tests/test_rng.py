"""Tests for the seeded RNG (WP-04). This is the one file the CI purity gate
allows to import the stdlib `random` module.
"""

from __future__ import annotations

import random

import pytest
from fabdraft_core.rng import rng_for


def test_same_seed_and_path_produce_identical_choice_sequences() -> None:
    rng_a = rng_for("seed-1", "pack", 1, 0)
    rng_b = rng_for("seed-1", "pack", 1, 0)
    pool = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
    seq_a = [rng_a.choice(pool) for _ in range(50)]
    seq_b = [rng_b.choice(pool) for _ in range(50)]
    assert seq_a == seq_b


def test_different_path_produces_a_different_sequence() -> None:
    rng_a = rng_for("seed-1", "pack", 1, 0)
    rng_b = rng_for("seed-1", "pack", 1, 1)
    pool = list(range(100))
    seq_a = [rng_a.choice(pool) for _ in range(30)]
    seq_b = [rng_b.choice(pool) for _ in range(30)]
    assert seq_a != seq_b


def test_different_seed_produces_a_different_sequence() -> None:
    rng_a = rng_for("seed-1", "pack", 1, 0)
    rng_b = rng_for("seed-2", "pack", 1, 0)
    pool = list(range(100))
    seq_a = [rng_a.choice(pool) for _ in range(30)]
    seq_b = [rng_b.choice(pool) for _ in range(30)]
    assert seq_a != seq_b


def test_call_order_across_purposes_does_not_affect_a_derived_rng() -> None:
    # rng_for(seed, "pack", 1) must draw the same sequence whether or not
    # some other rng_for(seed, "shuffle", ...) was used first (plan section
    # 6.1: "pack contents are stable regardless of agent timing or turn order").
    rng_for("seed-1", "shuffle", 1, 3, 5)  # unrelated purpose, used first
    rng_a = rng_for("seed-1", "pack", 1)
    rng_b = rng_for("seed-1", "pack", 1)
    assert [rng_a.choice(range(1000)) for _ in range(10)] == [
        rng_b.choice(range(1000)) for _ in range(10)
    ]


def test_isolated_from_global_random_module_state() -> None:
    rng_a = rng_for("seed-1", "x")
    baseline = [rng_a.choice(range(1000)) for _ in range(10)]

    random.seed(999999)
    random.random()
    random.random()

    rng_b = rng_for("seed-1", "x")
    again = [rng_b.choice(range(1000)) for _ in range(10)]
    assert baseline == again


def test_choice_raises_on_empty_sequence() -> None:
    rng = rng_for("s", "x")
    with pytest.raises(ValueError, match="empty"):
        rng.choice([])


def test_weighted_choice_raises_on_empty_or_non_positive_weights() -> None:
    rng = rng_for("s", "x")
    with pytest.raises(ValueError):
        rng.weighted_choice({})
    with pytest.raises(ValueError):
        rng.weighted_choice({"a": 0.0, "b": 0.0})


def test_weighted_choice_is_deterministic_and_respects_zero_weight_exclusion() -> None:
    rng_a = rng_for("seed-1", "weights")
    rng_b = rng_for("seed-1", "weights")
    weights = {"never": 0.0, "always": 1.0}
    seq_a = [rng_a.weighted_choice(weights) for _ in range(20)]
    seq_b = [rng_b.weighted_choice(weights) for _ in range(20)]
    assert seq_a == seq_b
    assert all(v == "always" for v in seq_a)


def test_weighted_choice_favors_higher_weight_over_many_draws() -> None:
    rng = rng_for("seed-1", "weights-stat")
    weights = {"common": 0.9, "rare": 0.1}
    draws = [rng.weighted_choice(weights) for _ in range(2000)]
    common_ratio = draws.count("common") / len(draws)
    assert 0.8 < common_ratio < 1.0


def test_shuffle_returns_a_new_list_and_does_not_mutate_input() -> None:
    rng = rng_for("seed-1", "shuffle-test")
    original = [1, 2, 3, 4, 5]
    original_copy = list(original)
    shuffled = rng.shuffle(original)
    assert original == original_copy
    assert sorted(shuffled) == sorted(original)
    assert shuffled is not original


def test_shuffle_is_deterministic_for_the_same_derived_rng_path() -> None:
    seq = list(range(20))
    rng_a = rng_for("seed-1", "shuffle", 1, 3, 2)
    rng_b = rng_for("seed-1", "shuffle", 1, 3, 2)
    assert rng_a.shuffle(seq) == rng_b.shuffle(seq)
