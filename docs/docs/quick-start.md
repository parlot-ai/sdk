---
title: Quick Start
description: Install Parlot and instrument a LiveKit agent in minutes.
sidebar_position: 1
---

# Quick Start

Parlot is an open-source SDK and instrumentation stack for multi-agent observability. Start with LiveKit Agents. The hosted analysis platform (dashboard, goal scoring, graphs) is commercial; the self-host platform is licensed under BSL 1.1 (free for your own agents and agents you operate for clients; converts to Apache 2.0 in 2030). Enterprise governance features (multi-org, SSO, audit) require an EE license key.

## Install

Install the instrumentation package using `pip` or `uv`:

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
export PARLOT_ENDPOINT=https://<your-collector-host>:4318
export PARLOT_API_KEY=<org-scoped-key>
```

Mint the API key in Parlot **Settings → API Keys**. For recording, enable Settings → Recording (or `configure(record=True)`). Org LiveKit integration is optional — it speeds up audio confirmation via egress webhooks; without it, audio still uploads to R2 and confirms when you open the session.

## Next

- [Core concepts](./concepts.md)
- [LiveKit guide](./guides/livekit.md)
- [API Reference](./api/index.mdx)
