"""attrs.gen.ts stays in sync with attrs.py."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ATTRS_PY = ROOT / "packages/core/src/parlot/core/attrs.py"
ATTRS_GEN_TS = ROOT / "packages/core-ts/src/attrs.gen.ts"
GENERATE = ROOT / "scripts/generate_attrs_ts.py"


def _python_constants() -> list[tuple[str, str]]:
    """Mirror scripts/generate_attrs_ts.py _collect_assignments for core attrs."""
    tree = ast.parse(ATTRS_PY.read_text(encoding="utf-8"), filename=str(ATTRS_PY))
    values: dict[str, str] = {}
    order: list[str] = []

    def _record(name: str, value: str) -> None:
        if name not in values:
            order.append(name)
        values[name] = value

    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        name = target.id
        if not (name.startswith("ATTR_") or name.startswith("EVENT_") or name.startswith("SPAN_")):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            _record(name, node.value.value)
        elif isinstance(node.value, ast.Name):
            _record(name, values[node.value.id])
    return [(name, values[name]) for name in order]


def _typescript_constants(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("export const "):
            continue
        # export const NAME = "value" as const;
        rest = line.removeprefix("export const ")
        name, _, tail = rest.partition(" = ")
        value = tail.removeprefix('"').split('"')[0]
        out.append((name, value))
    return out


def test_attrs_gen_ts_matches_attrs_py() -> None:
    subprocess.run(
        [sys.executable, str(GENERATE)],
        cwd=ROOT,
        check=True,
    )
    py_entries = _python_constants()
    ts_entries = _typescript_constants(ATTRS_GEN_TS.read_text(encoding="utf-8"))
    assert py_entries == ts_entries
