# apps/web (not yet scaffolded)

This will be the React 18 + TypeScript + Vite + Tailwind + Zustand frontend
(technical plan section 4.2, WP-19 onward).

It is intentionally empty as of this commit: the development environment
this repo was scaffolded in has a `node` binary but no working `npm` /
`npx` / `corepack`, so `package.json`, Vite config, and generated TypeScript
contract types cannot be installed or verified here. See
`docs/decisions/ADR-0001-uv-workspace-and-deferred-web-tooling.md`.

Before starting WP-19, confirm `npm install` works in your environment, then
scaffold Vite here and wire up `contracts` → TypeScript codegen (mirroring
`scripts/generate_contract_models.py` on the Python side) and the real
`eslint`/`tsc` steps in `.github/workflows/ci.yml`'s `web` job.
