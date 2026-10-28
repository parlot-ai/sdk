# Agent notes (SDK)

Public open-source SDK. Stay inside this repository.

## Tooling

- Python workspace: **uv** (`uv sync --group dev`, `uv run pytest` from the repo root). Do not use pip or poetry for packages.
- Docs site: **Bun** (`cd docs && bun start`).

## Documentation

User-facing docs live under [`docs/content/docs/`](docs/content/docs/) (App Guide + SDK docs).

**Audience:** developers who already build voice AI agents on LiveKit, Pipecat, LangGraph, or
similar frameworks.
Keep framework and OpenTelemetry terms (`AgentSession`, Room Composite egress, OTel/OTLP, GenAI
semconv, SIP, `parlotize()` kwargs). Skip pedantic expansions of API/UI for this audience.

**Voice:**
- Prefer clear product language; minimize Parlot-internal ingest jargon (for example “lazy R2 HEAD
  reconcile”) and marketing contrast (“not another dashboard…”).
- Prefer positive phrasing: state what something does. Avoid “does X, not Y” feature contrast.
- Expand product-specific terms on first use (e.g. “personally identifiable information (PII)”
  before “PII”). Prefer common terms over obscure acronyms (e.g. PII redaction rather than DLP).
- Public env-var docs: only customer-facing vars. Do not document internal compare/debug switches.

Skip hand-editing generated surfaces (`docs/content/docs/sdk/changelog.md`, TypeScript attr dumps
under `docs/content/docs/sdk/typescript/`). Regenerate via docs scripts when needed.

## Git

Before starting any new implementation work, create a fresh branch from up-to-date `main` (`git fetch origin && git checkout main && git pull && git checkout -b <branch>`). Do not continue on an unrelated existing branch. Never push `main`. Land via branch + PR + squash-merge. Conventional Commits feed Release Please. When the user asks to commit, push, or open a PR, load the `ship` skill (`.agents/skills/ship/SKILL.md`).

## Meta package dependency floors

**Manual — Release Please does not do this.** Whenever you change code under `packages/core` or `packages/instrumentation-*` that will ship a new package version (`feat` / `fix` / `perf` PR titles), plan a follow-up that raises the matching lower bounds in [`packages/meta/pyproject.toml`](packages/meta/pyproject.toml) so `"parlot[…]"` cannot resolve to pre-change wheels:

- `dependencies`: `parlot-core>=…`
- extras: `livekit` / `langgraph` / `pipecat` / `all` → matching `parlot-instrumentation-*>=…`
- related example pins / lockfiles when they pin those packages

Bump floors only after the new wheel is on PyPI (version from the Release Please release). Do not leave the meta floor one release behind.

## Local collector (optional)

Point an agent at a local OTLP receiver with `PARLOT_ENDPOINT` (this SDK appends `/v1/traces` and `/v1/metrics`). See [README.md](README.md).

## Source of truth

- [CONTRIBUTING.md](CONTRIBUTING.md) — PR titles and releases
- [README.md](README.md) — packages, examples, local dev
