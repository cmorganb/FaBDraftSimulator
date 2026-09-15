# FaBDraftSimulator

A training simulator for *Flesh and Blood* TCG booster draft, built against
the rules-accurate procedure for *Usurp the Shadow Throne* (set code `IAR`).
See [`FaBDraftSimulator-technical-plan.md`](./FaBDraftSimulator-technical-plan.md)
for the full specification, work breakdown, and status tracking conventions
(`docs/status/INDEX.md`).

**Not affiliated with or endorsed by Legend Story Studios.** Flesh and Blood
is a trademark of Legend Story Studios. No card text, card images, or other
Legend Story Studios IP is committed to this repository; card data is fetched
or supplied locally (see `scripts/ingest_set.py` and
`scripts/ingest_cardvault.py`) into `data/`, which is entirely gitignored
except the synthetic `data/fixtures/` and `data/config/` directories. This
is a personal, non-commercial training tool.

## Status

Early scaffolding. The Python core engine is being built first (see
`docs/status/INDEX.md`); the web UI (`apps/web`) is not yet set up — this
development environment currently lacks a working `npm`, so frontend work is
deferred to a later session (`docs/decisions/ADR-0001`).

## Setup (core engine / CLI / tests)

Requires [`uv`](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync --all-packages --dev
uv run pytest
uv run ruff check .
uv run mypy --strict packages/core
```

## Repository layout

See technical plan section 4.3 for the target layout. In short:
`contracts/` holds the JSON Schemas that are the source of truth for every
cross-package payload; `packages/core` is the pure, offline draft engine;
`packages/agents` and `packages/exports` and `apps/*` build on top of it.

Full onboarding docs, data acquisition walkthrough, and a source-to-rule
mapping land with WP-25.
