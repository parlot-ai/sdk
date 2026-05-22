# parlot-instrumentation-livekit

LiveKit span processor and `platform.ref.*` attributes for Parlot session resolve.

## Usage

```python
from parlot.instrumentation.livekit import configure

configure()

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    ...
```

`configure()` bootstraps one Parlot `session.id` per job on LiveKit's `job_entrypoint` span and exports a child `conversation.session` root for ingestion. Room metadata is captured when `JobContext.connect()` completes.

Set `PARLOT_ENDPOINT` (and optionally `PARLOT_API_KEY`) in the environment, or pass `endpoint=` / `api_key=` to `configure()`.

**Span processor:** use OpenTelemetry's default synchronous multi-processor layout from `configure()`. Wrapping Parlot's processor in `ConcurrentMultiSpanProcessor` is unsupported.

```bash
uv sync --extra dev
uv run pytest -q
```

Version and changelog are managed by [release-please](https://github.com/googleapis/release-please) at the repo root (`release-please-config.json` → this package path).
