---
title: Quick Start
description: Install Parlot and instrument a LiveKit agent in minutes.
sidebar_position: 1
---

# Quick Start

Parlot is an open-source SDK and instrumentation stack for multi-agent observability. Start with LiveKit Agents.

## Install

From a release tag:

```toml
# Consumer pyproject.toml
[tool.uv.sources]
parlot-core = { git = "https://github.com/parlot-ai/sdk.git", subdirectory = "packages/core", tag = "v0.1.0" }
parlot-instrumentation-livekit = { git = "https://github.com/parlot-ai/sdk.git", subdirectory = "packages/instrumentation-livekit", tag = "v0.1.0" }
```

Tag both packages at the same release. `uv lock` pins the commit SHA.

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
export PARLOT_ENDPOINT=https://<your-collector-host>:4318
export PARLOT_API_KEY=<org-scoped-key>
```

Mint the API key in Parlot **Settings → API Keys**. For recording, enable Settings → Recording (or `configure(record=True)`). Org LiveKit integration is optional — it speeds up audio confirmation via egress webhooks; without it, audio still uploads to R2 and confirms when you open the session.

## Next

- [Core concepts](./concepts.md)
- [LiveKit integration guide](./guides/livekit.md)
- [Deep dive: recording & webhooks](./guides/livekit-integration.md)
