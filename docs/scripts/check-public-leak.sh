#!/usr/bin/env bash
# Fail if public docs build output contains private-content markers.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${ROOT}/build"
if [[ ! -d "$BUILD" ]]; then
  echo "No build/ directory — run bun run build first" >&2
  exit 1
fi

PATTERNS=(
  'private-docs'
  '/internal-docs/'
  'gtm-strategy.md'
  'financial-plan.md'
  'SESSION_CLOSE_CONTRACT.md'
  'CONVERSATION_CONTRACT.md'
)

FAILED=0
for pat in "${PATTERNS[@]}"; do
  if grep -R --include='*.html' -F "$pat" "$BUILD" >/dev/null 2>&1; then
    echo "LEAK GUARD: found forbidden pattern in public build: $pat" >&2
    grep -R --include='*.html' -F "$pat" "$BUILD" | head -5 >&2 || true
    FAILED=1
  fi
done

if [[ "$FAILED" -ne 0 ]]; then
  exit 1
fi
echo "Public leak check passed."
