# Blocked items

When a work package discovers that a dependency, contract, or grounded fact
it needs is wrong, missing, or unresolved in a way that blocks progress
without guessing, add an entry below rather than working around it (plan
section 15, handoff protocol).

## Format

```
## WP-XX: <short title>
- **Date:** YYYY-MM-DD
- **Blocked on:** <what is missing/wrong>
- **Why it can't be worked around:** <reason a guess/workaround would be unsafe>
- **Needed from:** <human action, e.g. "paste TRP excerpt into docs/sources/",
  or "resolve VERIFY item S9">
```

## WP-01: plan section 2.4 S3 (total set size) contradicts S4 (rarity split)
- **Date:** 2026-09-14
- **Blocked on:** S3 states "Set size: 263 cards"; S4's own itemized rarity
  split (2 Fabled + 27 Marvel + 5 Legendary + 40 Majestic + 66 Rare + 133
  Common + 16 Basic) sums to **289**, not 263.
- **Why it can't be worked around:** These are both stated as `VERIFIED` in
  the plan's own ledger. Silently picking one would either under- or
  over-count the fixture set and, later, the real IAR set - exactly the
  "fabricated card data" failure mode section 0 item 3 warns against. This
  is a document error, not a code bug.
- **What was done in the meantime:** `scripts/generate_fixture_set.py` and
  `data/config/iar.expected_counts.json` use the itemized S4 breakdown
  (total 289) since it's what pack generation (WP-05) will actually key off
  of, and both are commented with this discrepancy. Not silently resolved -
  flagged here per section 0 item 3.
- **Needed from:** A human should recheck
  https://fabtcg.com/products/booster-set/iar/ (or the official IAR
  spoiler/checklist once fully released) and correct whichever of S3/S4 is
  wrong in `FaBDraftSimulator-technical-plan.md`, then update
  `data/config/iar.expected_counts.json` if the itemized breakdown turns out
  to be the one that's wrong.

## WP-01: upstream Basic-rarity shortcode not independently confirmed
- **Date:** 2026-09-14
- **Blocked on:** `documentation/abbreviations.md` in
  `the-fab-cube/flesh-and-blood-cards` (retrieved 2026-09-14) lists rarity
  codes C/R/S/M/L/F/T/V/P but not one for Basic. `scripts/ingest_set.py`
  infers `"B"` (the only unused letter consistent with the rest of the
  scheme) - see `RARITY_MAP` and its comment.
- **Why it can't be worked around:** Real IAR card data isn't published yet
  (R1), so this can't be tested against a real Basic-rarity card row.
- **Needed from:** Once upstream publishes IAR (or any set) card data,
  confirm a known Basic-rarity card's `printings[].rarity` value before
  trusting `RARITY_MAP["B"]` for a real ingestion run (WP-02 should assert
  this rather than assume it).
