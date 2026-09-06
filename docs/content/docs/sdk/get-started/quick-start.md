---
title: Quick Start
description: Production voice AI observability — instrument a LiveKit agent in minutes.
sidebar_position: 1
---

# Quick Start

**Know if your voice agent is actually working.** Parlot’s MIT `configure()` sidecar instruments [LiveKit Agents](https://docs.livekit.io/agents/) — Cloud, self-hosted, or [LiveKit on Telnyx](https://telnyx.com/products/livekit-on-telnyx) — and models each call as turns: timeline, multi-agent graph, and goal completion with an evidence trail to the proving turns and audio.

## Install

```bash
# Using pip
pip install parlot-instrumentation-livekit

# Or using uv
uv add parlot-instrumentation-livekit

# Or via the parlot meta-package
pip install "parlot[livekit]"
```

## Instrument

Call `configure()` before constructing `AgentSession`, then `await ctx.connect()` before `session.start()`:

```python
from parlot.instrumentation.livekit import configure

configure()

from livekit.agents import AgentSession, JobContext, WorkerOptions, cli


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(...)
    await session.start(agent=..., room=ctx.room)
```

## Environment

```bash
export PARLOT_ENDPOINT=https://ingest.parlot.ai
export PARLOT_API_KEY=<org-scoped-key>
```

Mint the API key in Parlot **Settings → API Keys**. For recording, enable Settings → Recording (or `configure(record=True)`). Audio uploads to R2 and confirms when you open the session (lazy R2 HEAD reconcile).

## Next

- [Core concepts](/docs/sdk/get-started/concepts)
- [LiveKit guide](/docs/sdk/guides/livekit)
- [Python API Reference](/docs/sdk/python)
- [TypeScript Reference](/docs/sdk/typescript)
- Already running LangGraph / LangChain alongside voice? See the [LangGraph guide](/docs/sdk/guides/langgraph).

## License

Instrumentation is **MIT**. The companion analysis platform is **BSL 1.1**: free production use up to 4,000 turns/month for your own agents and agents you operate for clients; above that, or to offer Parlot as a hosted service, requires a commercial license. Each version converts to Apache 2.0 four years after its first public release. Enterprise governance features require an EE license key.
