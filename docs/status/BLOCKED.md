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

## RESOLVED (2026-09-14, WP-07): section 6.2's "never receives the same pack twice" invariant is wrong

Plan section 6.2 states as an invariant: "A seat never receives the same
pack twice within a round." This directly contradicts the plan's *own*
glossary (section 17): "Wheel: A pack returning to a seat after passing
around the pod (with 14 cards and 8 seats, picks 9 to 14 come from wheeled
packs)." It's also provably false by the pass-rotation math: with an 8-seat
pod, the pack originating at seat O is back at seat O after exactly 8
passes, i.e. at pick 9 - which happens every round, for every seat, for 6
of the 8 packs each seat handles (picks 1-6's origins wheel back at picks
9-14; picks 7-8's origins don't, since 7+8=15 and 8+8=16 exceed the 14-pick
round).

**Resolved by implementing the correct (glossary-consistent) behavior**:
real shuffle-then-pass (TRP 8.2.1) naturally produces wheeling, and
`fabdraft_core.draft.engine` does exactly that. The false invariant is not
asserted anywhere in code; `test_wheeling_matches_the_plan_glossary`
(`packages/core/tests/test_draft_engine.py`) pins the actual, correct
behavior instead. See `docs/status/WP-07.md`.

## RESOLVED (2026-09-14): plan section 2.4 S3/S4 rarity-count discrepancy

Original entry (2026-09-14): S3 stated "Set size: 263 cards" while S4's own
itemized rarity split (2 Fabled + 27 Marvel + 5 Legendary + 40 Majestic + 66
Rare + 133 Common + 16 Basic) summed to 289, not 263 - and neither number
was actually right.

**Resolved by real data.** The user provided a full Card Vault
(cardvault.fabtcg.com) export of IAR at `data/IAR/` (gitignored - real LSS
card text/images, never committed, plan section 11). Ingested via the new
`scripts/ingest_cardvault.py` (see docs/status/WP-05.md). The real,
confirmed rarity split is:

| Rarity | Plan S4 said | Real (Card Vault) |
|---|---|---|
| Fabled | 2 | 2 |
| Marvel | 27 | **3** |
| Legendary | 5 | **4** |
| Majestic | 40 | 40 |
| Rare | 66 | 66 |
| Common | 133 | 133 |
| Basic | 16 | **14** |
| **Total** | 263 (S3) / 289 (S4 sum) | **262** |

Plan section 2.4's S4 table substantially overstated Marvel and Basic, and
slightly overstated Legendary. `data/config/iar.expected_counts.json`,
`scripts/generate_fixture_set.py` (`FIXTURE` is now a 262-card set matching
this real breakdown), and `data/fixtures/fixture_set.json` were all updated
accordingly. `FaBDraftSimulator-technical-plan.md` itself has not been
edited (out of scope for a code agent to rewrite the spec document), but
every place in code/config that consumed S4's numbers has been corrected -
future readers should treat this entry, not S4, as authoritative for IAR's
rarity counts until the plan document itself is corrected.

## RESOLVED (2026-09-14): upstream Basic-rarity shortcode

Original entry: the-fab-cube dataset's `documentation/abbreviations.md`
didn't list a rarity shortcode for Basic, so `scripts/ingest_set.py`
inferred `"B"`.

**Resolved by real data** (a different source, Card Vault, not
the-fab-cube - see above): `rarity: "basic"` is the literal value used, and
`scripts/ingest_cardvault.py`'s `RARITY_WORD_MAP` maps it to `"B"` directly,
no inference needed. The the-fab-cube path's inferred `"B"` in
`scripts/ingest_set.py` remains unverified against that *specific* dataset
(it's still an unpopulated placeholder for IAR, see below) but is no longer
blocking anything since Card Vault is now the working real-data source.

## Still open: the-fab-cube dataset has no real IAR card rows

- **Date:** 2026-09-14 (last checked; not re-verified after the Card Vault
  data arrived)
- **Blocked on:** `the-fab-cube/flesh-and-blood-cards`'s `IAR` set entry was
  a placeholder with a redacted name and no card rows as of this date.
- **Why it can't be worked around:** N/A - not actually blocking anything
  anymore. `scripts/ingest_cardvault.py` + `data/IAR/` (Card Vault) is now
  the working real-data path; `scripts/ingest_set.py` (the-fab-cube) is kept
  as a second, independent path but has no real IAR data to run against.
- **Needed from:** Nothing urgent. If the-fab-cube later publishes IAR data,
  it would be worth cross-checking its rarity counts against the Card Vault
  numbers above as an independent confirmation, but this is not required
  for any downstream WP.

## New, non-blocking limitations found via real data (2026-09-14)

Not blockers - each has a concrete, documented handling already in place.
Listed here so the next agent doesn't have to rediscover them:

- **Variable cost/power ("X"/"*").** Two real IAR cards have a
  cost or power of `"X"`/`"*"` instead of an integer. `Card.cost`/`.power`
  can't represent "variable" - `scripts/ingest_cardvault.py`'s
  `parse_numeric` drops these to `null` and marks the card
  `data_complete: false` (caught by WP-02's gate; requires
  `--allow-incomplete` to load). A future WP could extend the contract with
  a `cost_is_variable: bool` if this ever matters for gameplay-adjacent
  logic - out of scope for drafting.
- **Pitch isn't always 1-3.** One real Fabled resource card has pitch 4.
  `contracts/card.schema.json`'s `pitch` field no longer restricts to an
  enum.
- **Not every "arena card" is Basic rarity or pack-excluded.** Real data
  has Common- and Legendary-rarity equipment that IS ordinary, draftable
  booster content - only a young hero's own dedicated weapon+arm-equipment
  is Basic-rarity/never-drafted (plan S10). See
  `fabdraft_core.packs.generator.is_pack_eligible` and
  `docs/status/WP-05.md`'s amendment.
- **IAR does contain DFCs** (plan D11/R5, now resolved), but only on 2
  non-young hero forms (a flip to "Usurper"). Since heroes are never
  drafted, D11's face-down-pile hiding rule never actually triggers for IAR
  limited. `Card.double_faced_with` is intentionally left `null` for these.
- **`classes` sometimes contains the literal string `"Generic"`** instead
  of an empty list in the real data - normalized to `[]` during ingestion
  to match our own contract convention (plan section 5.1).
