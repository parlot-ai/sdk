#!/usr/bin/env bash
# Generate docs/docs/api/{configure,livekit,langgraph,core}.md from Python docstrings.
# Run via docs package prebuild / prestart (or manually: bash scripts/sync-api.sh).
set -euo pipefail

DOCS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "${DOCS_ROOT}/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is required to generate API docs from Python docstrings" >&2
  echo "  install: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

cd "${REPO_ROOT}"
uv run python docs/scripts/generate-api.py
