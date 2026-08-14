# Agent notes (SDK)

Public open-source SDK. Stay inside this repository.

## Tooling

- Python workspace: **uv** (`uv sync --group dev`, `uv run pytest` from the repo root). Do not use pip or poetry for packages.
- Docs site: **Bun** (`cd docs && bun start`).

## Git

Never push `main`. Land via branch + PR + squash-merge. Conventional Commits feed Release Please. When the user asks to commit, push, or open a PR, load the `ship` skill (`.agents/skills/ship/SKILL.md`).

## Local collector (optional)

Point an agent at a local OTLP receiver with `PARLOT_ENDPOINT` (this SDK appends `/v1/traces` and `/v1/metrics`). See [README.md](README.md).

## Source of truth

- [CONTRIBUTING.md](CONTRIBUTING.md) — PR titles and releases
- [README.md](README.md) — packages, examples, local dev
