#!/usr/bin/env python3
"""Generate TypeScript attribute constants from parlot.core.attrs (single source of truth)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ATTRS_PY = ROOT / "packages/core/src/parlot/core/attrs.py"
OUT_TS = ROOT / "packages/core-ts/src/attrs.gen.ts"


def _collect_assignments(tree: ast.Module) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        name = target.id
        if not (name.startswith("ATTR_") or name.startswith("EVENT_")):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            raise ValueError(f"{name}: expected string constant in attrs.py")
        out.append((name, node.value.value))
    return out


def _render_ts(entries: list[tuple[str, str]]) -> str:
    lines = [
        "/**",
        " * AUTO-GENERATED from packages/core/src/parlot/core/attrs.py",
        " * Do not edit manually. Run: uv run python scripts/generate_attrs_ts.py",
        " */",
        "",
    ]
    for name, value in entries:
        lines.append(f'export const {name} = "{value}" as const;')
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    source = ATTRS_PY.read_text(encoding="utf-8")
    entries = _collect_assignments(ast.parse(source, filename=str(ATTRS_PY)))
    if not entries:
        raise SystemExit(f"No ATTR_/EVENT_ constants found in {ATTRS_PY}")

    OUT_TS.parent.mkdir(parents=True, exist_ok=True)
    OUT_TS.write_text(_render_ts(entries), encoding="utf-8")
    print(f"Wrote {len(entries)} constants to {OUT_TS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
