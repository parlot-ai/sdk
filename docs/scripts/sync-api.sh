#!/usr/bin/env bash
# Generate docs/docs/api/{configure,livekit,langgraph,core}.md from docs-data/api.json.
# Run via docs package prebuild / prestart (or manually: bash scripts/sync-api.sh).
set -euo pipefail

DOCS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

bun run "${DOCS_ROOT}/scripts/generate-api.ts"
