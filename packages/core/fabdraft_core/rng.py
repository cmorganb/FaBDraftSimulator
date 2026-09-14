"""The only source of randomness in fabdraft_core (plan section 4.1 item 2:
"all randomness flows from one injected seeded RNG"). CI's purity gate greps
for `random.` outside this file - nowhere else in packages/core may import
the stdlib `random` module.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping, Sequence
from typing import TypeVar

T = TypeVar("T")
K = TypeVar("K")


class SeededRng:
    """A deterministic, seeded random source. Two SeededRng instances built
    from the same seed produce identical sequences of choices.
    """

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)  # noqa: S311 - deterministic by design, not crypto

    def choice(self, seq: Sequence[T]) -> T:
        if not seq:
            raise ValueError("choice() called on an empty sequence")
        return self._random.choice(seq)

    def weighted_choice(self, weights: Mapping[K, float]) -> K:
        """Pick one key from `weights`, keyed by relative weight. Weights
        need not sum to 1 - they are normalized. Raises ValueError if empty
        or all weights are non-positive, rather than silently returning an
        arbitrary key (plan section 6.1: never silently relax constraints).
        """
        if not weights:
            raise ValueError("weighted_choice() called with no candidates")
        keys = list(weights.keys())
        values = [float(w) for w in weights.values()]
        if sum(values) <= 0:
            raise ValueError("weighted_choice() called with no positive weight")
        return self._random.choices(keys, weights=values, k=1)[0]

    def shuffle(self, seq: Sequence[T]) -> list[T]:
        """Returns a new shuffled list; never mutates the input (core stays
        pure/functional - plan section 4.1 item 2).
        """
        result = list(seq)
        self._random.shuffle(result)
        return result


def rng_for(seed: str, *path: str | int) -> SeededRng:
    """Derive a deterministic sub-RNG for one purpose from a session seed and
    a path of identifiers, e.g. `rng_for(seed, "pack", round, pack_index)` or
    `rng_for(seed, "shuffle", round, pick, seat)` (plan sections 6.1, 6.2).
    Same seed + same path always yields the same sequence of draws,
    independent of call order or agent timing.
    """
    material = "|".join([seed, *(str(p) for p in path)])
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    derived_seed = int.from_bytes(digest[:8], byteorder="big")
    return SeededRng(derived_seed)
