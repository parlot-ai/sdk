#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Running ruff check..."
uv run ruff check packages/ scripts/ examples/

echo "==> Running mypy..."
uv run mypy
