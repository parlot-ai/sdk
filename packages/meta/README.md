# Parlot

Parlot shows whether production voice agents actually work — turns, handoffs, and goal completion with an evidence trail — not just that the pipeline returned 200s.

Call `parlotize()` once at startup. MIT OpenTelemetry instrumentation for LiveKit Agents (and LangGraph when you already run voice).

**Docs:** [parlot.ai/docs](https://parlot.ai/docs) · **Product:** [parlot.ai](https://parlot.ai)

## Install

```bash
pip install "parlot[livekit]"
# or: pip install "parlot[langgraph]"
# or: pip install "parlot[all]"
```

Or install an instrumentation package directly:

```bash
pip install parlot-instrumentation-livekit
# or: pip install parlot-instrumentation-langgraph
```

## Instrument (LiveKit)

Call `parlotize("…")` before constructing `AgentSession`, then `await ctx.connect()` before `session.start()`:

```python
from parlot.instrumentation.livekit import parlotize

parlotize("my-agent")

from livekit.agents import AgentSession, JobContext


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(...)
    await session.start(agent=..., room=ctx.room)
```

## Configure

```bash
export PARLOT_ENDPOINT=https://ingest.parlot.ai
export PARLOT_API_KEY=<org-scoped-key>
```

Mint the API key in Parlot **Settings → API Keys**.

## Next

- [Quick Start](https://parlot.ai/docs/sdk/get-started/quick-start)
- [LiveKit guide](https://parlot.ai/docs/guides/livekit)
- [LangGraph guide](https://parlot.ai/docs/guides/langgraph)
- [GitHub](https://github.com/parlot-ai/sdk)
