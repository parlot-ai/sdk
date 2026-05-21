# parlot-instrumentation-livekit

LiveKit span processor and `platform.ref.*` attributes for Parlot session resolve.

## Usage

```python
from parlot.instrumentation.livekit import configure, register_job_context

configure()

async def entrypoint(ctx: JobContext):
    await register_job_context(ctx)  # before connect — required for one session id per job
    await ctx.connect()
    ...
```

Set `PARLOT_ENDPOINT` (and optionally `PARLOT_API_KEY`) in the environment, or pass `endpoint=` / `api_key=` to `configure()`.

```bash
uv sync --extra dev
uv run pytest -q
```

Version and changelog are managed by [release-please](https://github.com/googleapis/release-please) at the repo root (`release-please-config.json` → this package path).
