# Agent notes (SDK)

Public open-source SDK. Stay inside this repository.

## Tooling

- Python workspace: **uv** (`uv sync --group dev`, `uv run pytest` from the repo root). Do not use pip or poetry for packages.
- Docs site: **Bun** (`cd docs && bun start`).

## Documentation

User-facing docs live under [`docs/content/docs/`](docs/content/docs/) (App Guide + SDK docs).

**Audience:** developers who already build agents on LiveKit, LangGraph, or similar frameworks.
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

When a breaking (or otherwise install-contract) change lands in `parlot-core` or an instrumentation adapter, bump the matching lower bounds in [`packages/meta/pyproject.toml`](packages/meta/pyproject.toml) (`parlot-core`, `livekit` / `langgraph` / `all` extras) so `"parlot[…]"` cannot resolve to pre-API wheels. Release Please will not do this automatically.

## Local collector (optional)

Point an agent at a local OTLP receiver with `PARLOT_ENDPOINT` (this SDK appends `/v1/traces` and `/v1/metrics`). See [README.md](README.md).

## Source of truth

- [CONTRIBUTING.md](CONTRIBUTING.md) — PR titles and releases
- [README.md](README.md) — packages, examples, local dev
