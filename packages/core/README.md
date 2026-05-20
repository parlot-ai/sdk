# parlot-core

Shared semantic conventions, base span processor, and utilities for all Parlot instrumentation packages.

## Contents

- `parlot.core.attrs` — all semconv string constants (`ATTR_GEN_AI_*`, `ATTR_LK_*`, Parlot extension namespaces); TypeScript mirror in `@parlot/core` (`packages/core-ts`, run `uv run python scripts/generate_attrs_ts.py` after edits)
- `parlot.core.session` — `SessionState` base dataclass for per-trace accumulators
- `parlot.core.pricing` — `DEFAULT_PRICES` table and `compute_cost()` helper
- `parlot.core.processor` — `ParlotBaseProcessor(SpanProcessor)` with shared span-mutation helpers
- `parlot.core.platform_refs` — generic `stamp_platform_refs()` for `platform.ref.*` triples (framework-specific registries live in each instrumentation package)

## Not for direct use

This package is a dependency of instrumentation packages (`parlot-instrumentation-livekit`, etc.). Import from those packages in your agent code, not from here directly.
