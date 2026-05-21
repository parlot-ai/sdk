#!/usr/bin/env python3
"""Generate TypeScript attribute constants from parlot attrs modules."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_ATTRS_PY = ROOT / "packages/core/src/parlot/core/attrs.py"
LK_ATTRS_PY = (
    ROOT
    / "packages/instrumentation-livekit/src/parlot/instrumentation/livekit/attrs.py"
)
OUT_CORE_TS = ROOT / "packages/core-ts/src/attrs.gen.ts"
OUT_LK_TS = ROOT / "packages/core-ts/src/attrs.livekit.gen.ts"


def _collect_assignments(tree: ast.Module) -> list[tuple[str, str]]:
    """Collect ATTR_/EVENT_ names to string values, including alias assignments."""
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
        if not (name.startswith("ATTR_") or name.startswith("EVENT_")):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            _record(name, node.value.value)
        elif isinstance(node.value, ast.Name):
            ref = node.value.id
            if ref not in values:
                raise ValueError(f"{name}: alias {ref} not defined yet")
            _record(name, values[ref])
        else:
            raise ValueError(f"{name}: expected string constant or alias")

    return [(name, values[name]) for name in order]


def _render_ts(entries: list[tuple[str, str]], source_label: str) -> str:
    lines = [
        "/**",
        f" * AUTO-GENERATED from {source_label}",
        " * Do not edit manually. Run: uv run python scripts/generate_attrs_ts.py",
        " */",
        "",
    ]
    for name, value in entries:
        lines.append(f'export const {name} = "{value}" as const;')
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    core_entries = _collect_assignments(
        ast.parse(CORE_ATTRS_PY.read_text(encoding="utf-8"), filename=str(CORE_ATTRS_PY))
    )
    lk_entries = _collect_assignments(
        ast.parse(LK_ATTRS_PY.read_text(encoding="utf-8"), filename=str(LK_ATTRS_PY))
    )
    if not core_entries:
        raise SystemExit(f"No ATTR_/EVENT_ constants found in {CORE_ATTRS_PY}")
    if not lk_entries:
        raise SystemExit(f"No ATTR_/EVENT_ constants found in {LK_ATTRS_PY}")

    OUT_CORE_TS.parent.mkdir(parents=True, exist_ok=True)
    OUT_CORE_TS.write_text(
        _render_ts(core_entries, "packages/core/src/parlot/core/attrs.py"),
        encoding="utf-8",
    )
    OUT_LK_TS.write_text(
        _render_ts(
            lk_entries,
            "packages/instrumentation-livekit/src/parlot/instrumentation/livekit/attrs.py",
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(core_entries)} constants to {OUT_CORE_TS.relative_to(ROOT)}")
    print(f"Wrote {len(lk_entries)} constants to {OUT_LK_TS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
