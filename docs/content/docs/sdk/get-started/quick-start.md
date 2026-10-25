---
title: Quick Start
description: Production voice AI observability — instrument LiveKit, Pipecat, or LangGraph agents in minutes.
sidebar_position: 1
---

# Quick Start

**Know if your voice AI agent is actually working.** Parlot’s MIT `parlotize()` instruments
production voice AI agents on [LiveKit Agents](https://docs.livekit.io/agents/),
[Pipecat](https://docs.pipecat.ai/), and [LangGraph](https://langchain-ai.github.io/langgraph/)
/ LangChain — and models each call as turns: timeline, multi-agent graph, and goal completion
with an evidence trail to the proving turns and audio.

This walkthrough uses LiveKit (Cloud, self-hosted, or
[LiveKit on Telnyx](https://telnyx.com/products/livekit-on-telnyx)). For Pipecat or LangGraph,
jump to the framework guides under [Next](#next).

## Install

```bash
# Using pip
pip install parlot-instrumentation-livekit

# Or using uv
uv add parlot-instrumentation-livekit

# Or via the parlot meta-package
pip install "parlot[livekit]"
# also: "parlot[pipecat]" · "parlot[langgraph]" · "parlot[all]"
```

## Instrument

Call `parlotize("…")` before constructing `AgentSession`, then `await ctx.connect()` before `session.start()`:

```python
from parlot.instrumentation.livekit import parlotize

parlotize("my-agent")

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

Create the API key in Parlot **Settings → API keys**. New tenants record session audio by
default (Settings → Recording allowlist `*`). Turn recording off with an empty allowlist or
`parlotize(record=False)`. On LiveKit, recording uses Room Composite egress; audio is available
when you open the session in Parlot.

## Next

- [Core concepts](/sdk/get-started/concepts)
- [LiveKit guide](/sdk/guides/livekit)
- [Pipecat guide](/sdk/guides/pipecat)
- [LangGraph guide](/sdk/guides/langgraph)
- [Python API Reference](/sdk/python)
- [TypeScript Reference](/sdk/typescript)

## License

Instrumentation is **MIT**. The companion analysis platform is **Business Source License 1.1
(BSL 1.1)**: free production use up to 4,000 turns/month for your own agents and agents you
operate for clients; above that, or to offer Parlot as a hosted service, requires a commercial
license. Each version converts to Apache 2.0 four years after its first public release.
Enterprise governance features require an Enterprise Edition (EE) license key.
