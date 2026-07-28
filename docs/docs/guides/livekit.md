---
title: LiveKit instrumentation
description: Integration checklist for parlot-instrumentation-livekit.
sidebar_position: 1
---

# LiveKit instrumentation

LiveKit span processor, egress recording to R2, and `platform.ref.*` attributes for Parlot session resolve.

## Integration checklist

Two steps are required for full Parlot behavior.

### 1. `configure()` at import (required)

Call before constructing `AgentSession` — patches `AgentSession.__init__`, sets up OTLP export to `PARLOT_ENDPOINT`, and installs turn/handoff/close event hooks.

```python
from parlot.instrumentation.livekit import configure

configure()
```

Optional: `agent_id=` for canonical deployment identity and `version=` for deployment version. See [Concepts](../concepts.md).

**Reliable patterns for LiveKit job processes:**

```python
configure(agent_id="restaurant-agent", version="0.1.0")
```

or set `PARLOT_AGENT_VERSION=0.1.0` at deploy/runtime.

### 2. `await ctx.connect()` before `session.start()` (required)

```python
async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(...)
    await session.start(agent=..., room=ctx.room)
```

Without `ctx.connect()` you may still see basic telemetry if you pass `room=ctx.room`, but you will **not** get room audio recording or a reliable `room_sid` for UI linking.

## Environment

Set `PARLOT_ENDPOINT` and `PARLOT_API_KEY` (org-scoped; mint in Settings → API Keys).

Recording policy precedence: job metadata → `configure(record=…)` → Settings → Recording via bootstrap.

Optional: `PARLOT_CAPTURE_CONTENT=false` to suppress prompt/response text in spans.

## Deeper guide

Recording, webhooks, bootstrap, and platform settings: [LiveKit integration](./livekit-integration.md).
