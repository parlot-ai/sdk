# parlot-core

Shared semantic conventions, base span processor, and utilities for all Parlot instrumentation packages.

## Contents

- `parlot.core.attrs` — GenAI semconv v1.41 pin, Conversation Contract / GenAI / voice span names, `ATTR_*` constants; TypeScript mirror in `@parlot/core` (`packages/core-ts`, run `uv run python scripts/generate_attrs_ts.py` after edits). Pin surface: `packages/core/genai_semconv.lock.json` (bump lock with `GENAI_SEMCONV_VERSION`)
- `parlot.core.export` — shared `ExportFilterSpanExporter` (contract ∪ GenAI ∪ voice allowlist)
- `parlot.core.configure` — `ConfigureProtocol` (keyword-only shared kwargs)
- `parlot.core.session` — `SessionState`, `get_active_session()` / `session_owned()` for cross-package coexistence
- `parlot.core.provider` — shared endpoint/api_key resolve + TracerProvider/OTLP bootstrap helpers
- `parlot.core.bootstrap` — `GET /v1/telemetry/bootstrap` → `ParlotRuntimeContext`
- `parlot.core.genai_content_capture` — `should_capture_genai_content` (generative AI / tool bodies; see [Concepts](https://parlot.ai/docs/concepts#generative-ai-content-capture))
- `parlot.core.processor` — `ParlotBaseProcessor(SpanProcessor)` with shared span-mutation helpers
- `parlot.core.platform_refs` — generic `stamp_platform_refs()` for `platform.ref.*` triples

## Not for direct use

This package is a dependency of instrumentation packages (`parlot-instrumentation-livekit`, `parlot-instrumentation-langgraph`, etc.). Import from those packages in your agent code, not from here directly.
