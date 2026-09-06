#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${DOCS_DIR}"
bun scripts/build-typedoc.ts
