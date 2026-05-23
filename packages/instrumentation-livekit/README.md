# parlot-instrumentation-livekit

LiveKit span processor, egress recording to R2, and `platform.ref.*` attributes for Parlot session resolve.

## Usage

```python
from parlot.instrumentation.livekit import configure

configure()

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    ...
```

`configure()` bootstraps one Parlot `session.id` per job, fetches telemetry bootstrap (org, R2, webhook signing key), and on `JobContext.connect()` may start **Room Composite Egress** to Cloudflare R2 when recording is enabled.

Set `PARLOT_ENDPOINT` and `PARLOT_API_KEY` in the environment. Configure the org **LiveKit integration** in Parlot (signing key + API secret) before recording works.

Recording policy: `PARLOT_RECORD_AGENTS` (`*`, allowlist, or unset=off) and job metadata `{ "record": true|false }`.

```bash
uv sync --extra dev
uv run pytest -q
```
