# parlot-instrumentation-livekit

Parlot shows whether production voice agents actually work — turns, handoffs, and goal completion with an evidence trail — not just that the pipeline returned 200s.

MIT OpenTelemetry instrumentation for [LiveKit Agents](https://docs.livekit.io/agents/) (Cloud, self-hosted, or [LiveKit on Telnyx](https://telnyx.com/products/livekit-on-telnyx)).

**Docs:** [LiveKit guide](https://parlot.ai/docs/guides/livekit) · [Quick Start](https://parlot.ai/docs/sdk/get-started/quick-start) · [parlot.ai](https://parlot.ai)

## Install

```bash
pip install parlot-instrumentation-livekit
# or: uv add parlot-instrumentation-livekit
# or: pip install "parlot[livekit]"
```

## Instrument

```python
from parlot.instrumentation.livekit import parlotize

parlotize("my-agent")

from livekit.agents import AgentSession, JobContext


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(...)
    await session.start(agent=..., room=ctx.room)
```

Two required steps:

- Call `parlotize("…")` **before** constructing `AgentSession`.
- Call `await ctx.connect()` **before** `session.start()`.

Pass `version=` to stamp a deployment version (`gen_ai.agent.version`); if omitted, Parlot stamps `"unknown"`.

## Configure

```bash
export PARLOT_ENDPOINT=https://ingest.parlot.ai
export PARLOT_API_KEY=<org-scoped-key>
```

Mint the API key in Parlot **Settings → API Keys**. Recording, session logs, and generative AI content capture are configured in Settings or via `parlotize(...)` kwargs — see the [LiveKit guide](https://parlot.ai/docs/guides/livekit).

## Next

- [Quick Start](https://parlot.ai/docs/sdk/get-started/quick-start)
- [LiveKit guide](https://parlot.ai/docs/guides/livekit)
- Examples: [`examples/livekit/`](../../examples/livekit/)
