# parlot-core

Shared semantic conventions, base span processor, and utilities for Parlot instrumentation packages — the MIT foundation behind [Parlot](https://parlot.ai) **production voice AI observability**.

Install [`parlot-instrumentation-livekit`](https://pypi.org/project/parlot-instrumentation-livekit/) (or `parlot[livekit]`) in agent code. This package is pulled in as a dependency; it is not the public `parlotize()` entrypoint.

## Contents

- `parlot.core.attrs` — GenAI semconv v1.41 pin, Conversation Contract / GenAI / voice span names, `ATTR_*` constants; TypeScript mirror in `@parlot/core` (`packages/core-ts`, run `uv run python scripts/generate_attrs_ts.py` after edits). Pin surface: `packages/core/genai_semconv.lock.json` (bump lock with `GENAI_SEMCONV_VERSION`)
- `parlot.core.export` — shared `ExportFilterSpanExporter` (contract ∪ GenAI ∪ voice allowlist)
- `parlot.core.parlotize` — `ParlotizeProtocol` (keyword-only shared kwargs)
- `parlot.core.session` — `SessionState`, `get_active_session()` / `session_owned()` for cross-package coexistence
- `parlot.core.provider` — shared endpoint/api_key resolve + TracerProvider/OTLP bootstrap helpers
- `parlot.core.bootstrap` — `GET /v1/telemetry/bootstrap` → `ParlotRuntimeContext`
- `parlot.core.genai_content_capture` — `should_capture_genai_content` (generative AI / tool bodies; see [Concepts](https://parlot.ai/docs/concepts#generative-ai-content-capture))
- `parlot.core.processor` — `ParlotBaseProcessor(SpanProcessor)` with shared span-mutation helpers
- `parlot.core.platform_refs` — generic `stamp_platform_refs()` for `platform.ref.*` triples

## Not for direct use

This package is a dependency of instrumentation packages (`parlot-instrumentation-livekit`, `parlot-instrumentation-langgraph`, etc.). Import from those packages in your agent code, not from here directly.

**Docs:** [parlot.ai/docs](https://parlot.ai/docs) · [GitHub](https://github.com/parlot-ai/sdk)
