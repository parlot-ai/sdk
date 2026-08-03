#!/usr/bin/env python3
"""Fail if GENAI_SEMCONV_VERSION changed without updating genai_semconv.lock.json.

Usage (from sdk repo root)::

    python scripts/check_genai_semconv_lock.py
    python scripts/check_genai_semconv_lock.py --base origin/main

Also validates that the lockfile matches ``attrs.py`` constants.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = REPO_ROOT / "packages" / "core" / "genai_semconv.lock.json"
ATTRS_PATH = REPO_ROOT / "packages" / "core" / "src" / "parlot" / "core" / "attrs.py"


def _git_diff_names(base: str) -> set[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            cwd=REPO_ROOT,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"error: git diff failed: {exc}", file=sys.stderr)
        sys.exit(2)
    return {line.strip() for line in out.splitlines() if line.strip()}


def _git_diff_attrs_version(base: str) -> bool:
    """True when GENAI_SEMCONV_VERSION assignment changed vs base."""
    try:
        out = subprocess.check_output(
            ["git", "diff", f"{base}...HEAD", "--", str(ATTRS_PATH.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"error: git diff attrs failed: {exc}", file=sys.stderr)
        sys.exit(2)
    for line in out.splitlines():
        if line.startswith(("+", "-")) and "GENAI_SEMCONV_VERSION" in line:
            if line.startswith(("+++", "---")):
                continue
            return True
    return False


def _validate_lock_matches_attrs() -> list[str]:
    errors: list[str] = []
    sys.path.insert(0, str(REPO_ROOT / "packages" / "core" / "src"))
    from parlot.core import attrs as a  # noqa: PLC0415

    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("version") != a.GENAI_SEMCONV_VERSION:
        errors.append(
            f"lock version {lock.get('version')!r} != GENAI_SEMCONV_VERSION "
            f"{a.GENAI_SEMCONV_VERSION!r}"
        )

    ops = [
        a.GEN_AI_OP_CHAT,
        a.GEN_AI_OP_EXECUTE_TOOL,
        a.GEN_AI_OP_INVOKE_AGENT,
        a.GEN_AI_OP_INVOKE_WORKFLOW,
    ]
    if lock.get("operations") != ops:
        errors.append(f"lock operations {lock.get('operations')!r} != {ops!r}")

    bases = [
        a.SPAN_GEN_AI_CHAT,
        a.SPAN_GEN_AI_EXECUTE_TOOL,
        a.SPAN_GEN_AI_INVOKE_AGENT,
        a.SPAN_GEN_AI_INVOKE_WORKFLOW,
    ]
    if lock.get("span_bases") != bases:
        errors.append(f"lock span_bases {lock.get('span_bases')!r} != {bases!r}")

    declared = set(lock.get("attrs") or [])
    known = {
        getattr(a, name)
        for name in dir(a)
        if name.startswith("ATTR_GEN_AI_") and isinstance(getattr(a, name), str)
    }
    missing = declared - known
    if missing:
        errors.append(f"lock attrs not defined in attrs.py: {sorted(missing)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        default="origin/main",
        help="git ref to diff against for version/lock co-change check",
    )
    parser.add_argument(
        "--skip-diff",
        action="store_true",
        help="only validate lock ↔ attrs (skip PR co-change check)",
    )
    args = parser.parse_args()

    if not LOCK_PATH.is_file():
        print(f"error: missing lockfile {LOCK_PATH}", file=sys.stderr)
        return 1

    errors = _validate_lock_matches_attrs()
    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1

    if not args.skip_diff:
        changed = _git_diff_names(args.base)
        attrs_rel = str(ATTRS_PATH.relative_to(REPO_ROOT))
        lock_rel = str(LOCK_PATH.relative_to(REPO_ROOT))
        if _git_diff_attrs_version(args.base) and lock_rel not in changed:
            print(
                "error: GENAI_SEMCONV_VERSION changed in attrs.py but "
                f"{lock_rel} was not updated in the same change",
                file=sys.stderr,
            )
            print(
                "Update packages/core/genai_semconv.lock.json when bumping the pin.",
                file=sys.stderr,
            )
            return 1
        # Quiet success path when attrs file touched for other reasons.
        if attrs_rel in changed and lock_rel not in changed and _git_diff_attrs_version(args.base):
            return 1

    print("genai_semconv.lock.json OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
