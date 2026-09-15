# Work package status index

Per plan section 15 handoff protocol: a WP is claimed by setting its row to
`IN PROGRESS` with a timestamp before work starts; claiming two WPs whose
dependency edges cross is forbidden. Each `DONE` row must have a matching
`docs/status/WP-XX.md` handoff doc.

| WP | Title | Depends | Status | Handoff doc |
|---|---|---|---|---|
| WP-00 | Repo, tooling, CI | - | DONE | [WP-00.md](./WP-00.md) |
| WP-01 | Set ingestion + fixture set | WP-00 | DONE | [WP-01.md](./WP-01.md) |
| WP-02 | Set validation gate | WP-01 | DONE | [WP-02.md](./WP-02.md) |
| WP-03 | Contracts + codegen | WP-00 | DONE | [WP-03.md](./WP-03.md) |
| WP-04 | Seeded RNG + event store | WP-03 | DONE | [WP-04.md](./WP-04.md) |
| WP-05 | Pack generator | WP-02, WP-04 | DONE | [WP-05.md](./WP-05.md) |
| WP-06 | Card model, indexes, legality | WP-02 | DONE | [WP-06.md](./WP-06.md) |
| WP-07 | Draft state machine | WP-04, WP-05 | DONE | [WP-07.md](./WP-07.md) |
| WP-08 | Information policy enforcement | WP-07 | DONE | [WP-08.md](./WP-08.md) |
| WP-09 | Deck build + validation | WP-06, WP-07 | DONE | [WP-09.md](./WP-09.md) |
| WP-10 | Pool and deck metrics + IAR tags | WP-09 | DONE | [WP-10.md](./WP-10.md) |
| WP-11 | Log writers | WP-07, WP-09 | DONE | [WP-11.md](./WP-11.md) |
| WP-12 | Replay | WP-11 | DONE | [WP-12.md](WP-12.md) |
| WP-13 | Exports | WP-09 | IN PROGRESS (2026-09-14) | - |
| WP-14 | Agent protocol + human adapter | WP-08 | IN PROGRESS (2026-09-14) | - |
| WP-15 | Heuristic agent | WP-14, WP-10 | NOT STARTED | - |
| WP-16 | LLM agent | WP-14 | NOT STARTED | - |
| WP-17 | CLI: single draft + batch sim | WP-12, WP-15 | NOT STARTED | - |
| WP-18 | API + session manager | WP-07, WP-14 | NOT STARTED | - |
| WP-19 | Web app shell + state | WP-18, WP-03 | NOT STARTED | - |
| WP-20 | Draft table screen | WP-19 | NOT STARTED | - |
| WP-21 | Review + deck build screens | WP-19, WP-09 | NOT STARTED | - |
| WP-22 | Report + replay viewer | WP-19, WP-11, WP-15 | NOT STARTED | - |
| WP-23 | Coach mode | WP-15, WP-16, WP-22 | NOT STARTED | - |
| WP-24 | Batch analytics | WP-17 | NOT STARTED | - |
| WP-25 | Docs and release | all | NOT STARTED | - |
| WP-26 | Hardening pass | all | NOT STARTED | - |

## Notes for the next agent

- WP-08 is done: `fabdraft_core.draft.views.build_agent_view` (see
  docs/status/WP-08.md) builds the per-pick `AgentView`, scoped to active
  pick windows only - there's no `ReviewView` yet (the plan names one in
  `Agent.review()` but never gives it a contract), so "own_pool visible
  during review" isn't reachable from this function. WP-14 should wire a
  real Agent's `pick()` call through `build_agent_view` in place of the
  engine's temporary `PickSource.get_pick(seat, list[Card], deadline_ms)`.
- WP-09 is done: `fabdraft_core.deck.builder.{legal_pool, validate_deck}`
  (see docs/status/WP-09.md) reaches all 9 `Violation.code` values with
  real CR citations, and also resolved the weapon/equipment-slot VERIFY
  item deferred from WP-06. No deck-build *orchestrator* exists yet
  (nothing emits HERO_SELECTED/DECK_CARD_ADDED/DECK_SUBMITTED/
  VALIDATION_RESULT events) - that's still open for whoever wires deck
  building into the event-sourced session (WP-18, most likely).
- WP-08 and WP-09 were built in parallel in separate git worktrees (this
  environment's `Agent` tool worktree isolation isn't available - "not in a
  git repository" error - so worktrees were created manually with `git
  worktree add`; do the same for any future parallel WP work here).
- **Found a second real spec contradiction** (see `docs/status/BLOCKED.md`,
  RESOLVED entries): plan section 6.2's invariant "a seat never receives
  the same pack twice within a round" is mathematically false for an
  8-seat/14-pick pod and contradicts the plan's own "Wheel" glossary entry.
  The engine implements real wheeling (verified against the glossary), not
  the false invariant - don't re-introduce it.
- `docs/sources/en-fab-{cr,trp}.txt` (full Comprehensive Rules / Tournament
  Rules text, kept locally by the user, not committed - see memory
  `rules-text-sources`) are the authoritative source for `# CR`/`# TRP`
  citations. Grep them before guessing at a rule number or a keyword list
  (class/talent supertypes, keyword ability wording, etc.) - WP-06 found
  and fixed a wrong hand-derived class/talent list this way.
- `Card` gained two required fields during WP-05: `is_expansion_slot: bool`
  and `object_type: enum["deck","arena","hero","token"]` (see
  `docs/status/WP-03.md`'s amendment notes) - any new Card-constructing test
  or script must include both.
- `apps/web` is an empty placeholder (no `package.json`) - the environment
  this repo was scaffolded in has no working `npm`. Confirm npm works before
  claiming WP-19+. See `docs/decisions/ADR-0001-uv-workspace-and-deferred-web-tooling.md`.
- **Real IAR card data is now available** at `data/IAR/` (a Card Vault
  export - manifest.json, cards.json, images/ - gitignored, real LSS IP,
  never commit it or anything derived from it). Ingest with
  `uv run python scripts/ingest_cardvault.py --in-dir data/IAR --out
  data/sets/IAR.json`, then `uv run python scripts/validate_set.py --in
  data/sets/IAR.json --allow-incomplete` (2 real cards have an
  unrepresentable variable cost/power - see `docs/status/BLOCKED.md`).
  `data/sets/` is also gitignored. Every WP should still default to
  developing against `FIXTURE` (262 cards, matching the real rarity split -
  no dependency on data the repo doesn't ship), but real data is there to
  sanity-check against, and WP-05's pack generator has been run against it
  successfully (1000 packs).
- **`docs/status/BLOCKED.md`'s S3/S4 total-mismatch entry is now RESOLVED**
  by real data: the true IAR rarity split is F2/V3/L4/M40/R66/C133/B14 =
  262 cards, not either of the plan's own numbers (263 or the S4 sum of
  289). Plan section 2.4 S4 substantially overstated Marvel (27 vs 3) and
  Basic (16 vs 14). `data/config/iar.expected_counts.json` and the whole
  `FIXTURE` set now use the real numbers.
- The-fab-cube (the *other* ingestion path, `scripts/ingest_set.py`) still
  has no real IAR data as of last check - Card Vault
  (`scripts/ingest_cardvault.py`) is the working real-data source.
- WP-11 is done: `fabdraft_core.logs.{markdown,session}` render
  `draft_log.md`/`session.json` from a real event log (see
  `docs/status/WP-11.md`). No deck-build orchestrator exists yet, so the
  "Deck build" section of every real log renders a `_Pending` marker until
  something (WP-18, most likely) emits `HERO_SELECTED`/`DECK_CARD_ADDED`/
  `DECK_CARD_REMOVED`/`DECK_SUBMITTED`/`VALIDATION_RESULT` events. Also:
  WP-07's events have no per-pick `time_used_ms` (only a pod-wide
  per-window clock advance) - flagged as a known limitation, not fixed here.
