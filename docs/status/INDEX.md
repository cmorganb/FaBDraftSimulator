# Work package status index

Per plan section 15 handoff protocol: a WP is claimed by setting its row to
`IN PROGRESS` with a timestamp before work starts; claiming two WPs whose
dependency edges cross is forbidden. Each `DONE` row must have a matching
`docs/status/WP-XX.md` handoff doc.

| WP | Title | Depends | Status | Handoff doc |
|---|---|---|---|---|
| WP-00 | Repo, tooling, CI | - | DONE | [WP-00.md](./WP-00.md) |
| WP-01 | Set ingestion + fixture set | WP-00 | DONE | [WP-01.md](./WP-01.md) |
| WP-02 | Set validation gate | WP-01 | NOT STARTED | - |
| WP-03 | Contracts + codegen | WP-00 | DONE | [WP-03.md](./WP-03.md) |
| WP-04 | Seeded RNG + event store | WP-03 | DONE | [WP-04.md](./WP-04.md) |
| WP-05 | Pack generator | WP-02, WP-04 | NOT STARTED | - |
| WP-06 | Card model, indexes, legality | WP-02 | NOT STARTED | - |
| WP-07 | Draft state machine | WP-04, WP-05 | NOT STARTED | - |
| WP-08 | Information policy enforcement | WP-07 | NOT STARTED | - |
| WP-09 | Deck build + validation | WP-06, WP-07 | NOT STARTED | - |
| WP-10 | Pool and deck metrics + IAR tags | WP-09 | NOT STARTED | - |
| WP-11 | Log writers | WP-07, WP-09 | NOT STARTED | - |
| WP-12 | Replay | WP-11 | NOT STARTED | - |
| WP-13 | Exports | WP-09 | NOT STARTED | - |
| WP-14 | Agent protocol + human adapter | WP-08 | NOT STARTED | - |
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

- WP-02 is the natural next pick: only depends on WP-01 (done), is Size S,
  and unblocks WP-05/WP-06 in parallel. WP-04 (done) is also a dependency
  for WP-05/WP-07.
- `apps/web` is an empty placeholder (no `package.json`) - the environment
  this repo was scaffolded in has no working `npm`. Confirm npm works before
  claiming WP-19+. See `docs/decisions/ADR-0001-uv-workspace-and-deferred-web-tooling.md`.
- Real IAR card data is not yet published upstream (checked
  2026-09-14, the-fab-cube dataset has only a placeholder `IAR` set entry).
  `data/fixtures/fixture_set.json` (set code `FIXTURE`, 289 cards) is the
  only working data source; do not build against an assumption that
  `data/sets/IAR.json` exists.
- **Read `docs/status/BLOCKED.md` before trusting plan section 2.4's S3**
  ("263 cards") - it contradicts S4's own rarity-split sum (289). The
  fixture set and `data/config/iar.expected_counts.json` use 289
  (internally consistent with S4); this needs human resolution against the
  official IAR product page.
