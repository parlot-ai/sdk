# Agent notes (SDK)

Public open-source SDK. Stay inside this repository.

## Tooling

- Python workspace: **uv** (`uv sync --group dev`, `uv run pytest` from the repo root). Do not use pip or poetry for packages.
- Docs site: **Bun** (`cd docs && bun start`).

## Documentation

In user-facing docs (under `docs/content/docs/`):
- Minimize jargon; use clear, accessible product language.
- Never use acronyms without introducing and expanding them on first use (e.g. "personally identifiable information (PII)" before using "PII"). Prefer common, widely understood terms over obscure acronyms (e.g. PII redaction rather than DLP).

## Git

Before starting any new implementation work, create a fresh branch from up-to-date `main` (`git fetch origin && git checkout main && git pull && git checkout -b <branch>`). Do not continue on an unrelated existing branch. Never push `main`. Land via branch + PR + squash-merge. Conventional Commits feed Release Please. When the user asks to commit, push, or open a PR, load the `ship` skill (`.agents/skills/ship/SKILL.md`).

## Meta package dependency floors

When a breaking (or otherwise install-contract) change lands in `parlot-core` or an instrumentation adapter, bump the matching lower bounds in [`packages/meta/pyproject.toml`](packages/meta/pyproject.toml) (`parlot-core`, `livekit` / `langgraph` / `all` extras) so `"parlot[…]"` cannot resolve to pre-API wheels. Release Please will not do this automatically.

## Local collector (optional)

Point an agent at a local OTLP receiver with `PARLOT_ENDPOINT` (this SDK appends `/v1/traces` and `/v1/metrics`). See [README.md](README.md).

## Source of truth

- [CONTRIBUTING.md](CONTRIBUTING.md) — PR titles and releases
- [README.md](README.md) — packages, examples, local dev
