"""Called-draft timing (plan section 2.2, WP-07).

# TRP A.3: recommended booster-draft per-pick time limits, keyed by the
# number of cards currently in the pack (verified verbatim against
# docs/sources/en-fab-trp.txt, not committed):
#   15-12 cards: 50s: 11-10: 40s; 9-8: 30s; 7-6: 20s; 5-4: 10s; 3-2: 5s;
#   1 card: no timer. "The recommended time limit for the review period is
#   1 minute."
"""

from __future__ import annotations

_TIMER_TABLE: tuple[tuple[range, int], ...] = (
    (range(12, 16), 50),
    (range(10, 12), 40),
    (range(8, 10), 30),
    (range(6, 8), 20),
    (range(4, 6), 10),
    (range(2, 4), 5),
)

REVIEW_WINDOW_SECONDS = 60  # TRP A.3


def timer_seconds_for_pack_size(cards_in_pack: int) -> int | None:
    """None means no timer (TRP A.3: a single remaining card is a forced
    pick with no time limit).
    """
    if cards_in_pack < 1:
        raise ValueError(f"cards_in_pack must be >= 1, got {cards_in_pack}")
    if cards_in_pack == 1:
        return None
    for size_range, seconds in _TIMER_TABLE:
        if cards_in_pack in size_range:
            return seconds
    # TRP A.3 only tabulates up to 15 cards (IAR packs start at 14
    # draftable, S9) - anything larger is out of scope for this product,
    # not a value to silently approximate.
    raise ValueError(f"no TRP A.3 timer entry for a {cards_in_pack}-card pack")
