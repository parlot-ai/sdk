#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/../../platform/packages/docs-theme"
DST="${ROOT}/vendor/docs-theme"
if [[ ! -d "$SRC" ]]; then
  echo "Theme source not found at $SRC (sibling platform checkout required)" >&2
  exit 1
fi
rm -rf "$DST/src"
cp -R "$SRC/src" "$DST/"
cp "$SRC/package.json" "$DST/"
# Bun copies file: deps into node_modules — refresh so builds pick up changes.
if command -v bun >/dev/null 2>&1; then
  (cd "$ROOT" && bun install --silent)
fi
echo "Synced @parlot/docs-theme -> vendor/docs-theme"
