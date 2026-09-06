#!/usr/bin/env python3
"""Dump scoped public API AST and parsed docstrings to JSON via Griffe.

Outputs docs-data/api.json used by docs/scripts/generate-api.ts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from griffe import load
from griffe._internal.encoders import JSONEncoder

REPO_ROOT = Path(__file__).resolve().parents[1]

SEARCH_PATHS = [
    str(REPO_ROOT / "packages" / "core" / "src"),
    str(REPO_ROOT / "packages" / "instrumentation-livekit" / "src"),
    str(REPO_ROOT / "packages" / "instrumentation-langgraph" / "src"),
]

DOCUMENTED_MODULES = [
    "parlot.core.configure",
    "parlot.core.metadata",
    "parlot.core.platform_refs",
    "parlot.core.escalation",
    "parlot.core.session",
    "parlot.instrumentation.livekit._auto",
    "parlot.instrumentation.livekit._events",
    "parlot.instrumentation.livekit._processor",
    "parlot.instrumentation.langgraph._auto",
    "parlot.instrumentation.langgraph._callbacks",
]


def dump_api(output_path: Path) -> None:
    data = {}
    for mod_name in DOCUMENTED_MODULES:
        mod = load(mod_name, search_paths=SEARCH_PATHS, docstring_parser="google")
        # Suppress volatile git commit hashes from source_link in committed snapshot
        if mod.package is not None:
            mod.package._git_info = None
        data[mod_name] = mod

    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, cls=JSONEncoder, full=True, sort_keys=True, indent=2)
    # Strip local workspace root paths so committed snapshot is deterministic across machines
    root_prefix = str(REPO_ROOT).replace("\\", "/").rstrip("/") + "/"
    serialized = serialized.replace(root_prefix, "")
    output_path.write_text(serialized + "\n", encoding="utf-8")
    print(f"Dumped API snapshot to {output_path.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump scoped API AST to JSON.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=REPO_ROOT / "docs-data" / "api.json",
        help="Target JSON file path (default: docs-data/api.json)",
    )
    args = parser.parse_args()
    dump_api(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
