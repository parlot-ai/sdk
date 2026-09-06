#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUTPUT_DIR="${REPO_ROOT}/dist/reference/python"
DOCS_PUBLIC_DIR="${REPO_ROOT}/docs/public/ref/python"

echo "Building Python API reference with pdoc..."
mkdir -p "${OUTPUT_DIR}"
cd "${REPO_ROOT}"

uv run pdoc parlot parlot.instrumentation.livekit parlot.instrumentation.langgraph \
  --output-directory "${OUTPUT_DIR}" \
  --docformat google

echo "Copying reference to docs public directory: ${DOCS_PUBLIC_DIR}"
mkdir -p "${DOCS_PUBLIC_DIR}"
cp -R "${OUTPUT_DIR}/." "${DOCS_PUBLIC_DIR}/"

echo "Python API reference build complete."
