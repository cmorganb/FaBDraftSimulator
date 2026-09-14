# ADR-0001: uv workspace for Python packages; defer `apps/web` setup

**Status:** Accepted
**Date:** 2026-09-14
**Related WPs:** WP-00, WP-03

## Context

Technical plan section 4.2 specifies `pyproject.toml` for the Python side
without naming a specific dependency manager, and section 4.3 lays out
`packages/core`, `packages/agents`, `packages/exports`, `apps/api`,
`apps/cli`, `apps/web` as siblings that will eventually depend on one
another (e.g. `apps/cli` on `packages/core` and `packages/agents`).

The build environment at implementation time has Python 3.12 and `uv`
0.11.28 available, but Node has only a bare `node` binary — no `npm`, `npx`,
or `corepack`. `apps/web` (React/Vite/TypeScript per section 4.2) cannot be
installed, built, or type-checked here.

## Decision

1. Use a **uv workspace** rooted at the repo root (`[tool.uv.workspace]
   members = ["packages/*", "apps/*"]`) rather than a single flat package or
   Poetry. Each package/app gets its own `pyproject.toml` and is
   independently installable; `packages/core` stays dependency-free of
   everything else, preserving the "pure, offline core" principle
   mechanically (a workspace member simply cannot `import` a package it
   hasn't declared a dependency on).
2. `apps/web` is created as an empty directory with a placeholder note only.
   No `package.json`, no Vite config, no generated TypeScript types are
   added this session. `.github/workflows/ci.yml`'s `web` job checks for
   `apps/web/package.json` and no-ops until it exists, so CI never silently
   claims to be running checks it isn't.
3. Contract codegen (WP-03) ships Python (pydantic) models only this
   session. TypeScript codegen is deferred to the WP that scaffolds
   `apps/web` with working npm.

## Consequences

- Nothing in Phase 0-2 (core engine, agents, CLI) is blocked by the missing
  npm, since none of it depends on `apps/web`.
- The uv workspace is a superset of a plain `pyproject.toml` and does not
  preclude switching tools later; no lock-in.
- Whoever picks up WP-19 (web app shell) must first confirm npm works in
  their environment and then add the `apps/web` `package.json`, TS codegen
  step, and real `eslint`/`tsc` CI steps — tracked in `docs/status/INDEX.md`.
