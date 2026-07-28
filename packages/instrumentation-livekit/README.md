# parlot-instrumentation-livekit

LiveKit span processor, egress recording to R2, and `platform.ref.*` attributes for Parlot session resolve.

## Integration checklist

Two steps are required for full Parlot behavior. All SDK examples follow this pattern.

### 1. `configure()` at import (required)

Call before constructing `AgentSession` — patches `AgentSession.__init__`, sets up OTLP export to `PARLOT_ENDPOINT`, and installs turn/handoff/close event hooks.

```python
from parlot.instrumentation.livekit import configure

configure()
```

Optional: `agent_id=` for canonical deployment identity and `version=` for deployment version. Full resolution order is in the [SDK README](../../README.md#agent-deployment-version).

#### What to expect for version

`configure(version=...)` resolves once at startup (first non-empty wins): `version=` kwarg → `__main__.__version__` / `VERSION` → `PARLOT_AGENT_VERSION` → local git short SHA (only when cwd has a `.git` directory).

If none resolve, `gen_ai.agent.version` is omitted. The platform Versions tab then stays empty (it filters `agent_version != ''`).

**LiveKit job processes:** with `python agent.py dev` (or spawned `job_proc` workers), `__main__` is LiveKit’s IPC entrypoint, not your agent file. A module-level `__version__` on `agent.py` often does **not** resolve. The parent `dev` watcher also skips `configure()` via `_is_livekit_dev_watch_parent`, so instrumentation runs in the child where `__main__` is not your entrypoint. Example dirs like `examples/restaurant-agent` usually have no `.git`, so the git SHA fallback also fails.

**Reliable patterns for LiveKit:**

```python
configure(agent_id="restaurant-agent", version="0.1.0")
```

or set `PARLOT_AGENT_VERSION=0.1.0` at deploy/runtime.

### 2. `await ctx.connect()` before `session.start()` (required)

Call explicitly in your `entrypoint`. Parlot patches `JobContext.connect` to:

- Refresh **`platform.ref.room_sid`** and room metadata on the live session span (paste-search and platform UI linking).
- Start **Room Composite Egress** to Cloudflare R2 when recording is enabled.

```python
async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(...)
    await session.start(agent=..., room=ctx.room)
```

**Without `ctx.connect()`** you may still see basic telemetry — turns, handoffs, session close — if you pass `room=ctx.room` to `session.start()`. You will **not** get:

- Room audio recording (egress to R2)
- A reliable `room_sid` on the session span for paste-search and UI linking

Always call `ctx.connect()` in production agents and in all Parlot examples.

## Environment

Set `PARLOT_ENDPOINT` and `PARLOT_API_KEY`. The API key is **org-scoped** — mint it in Parlot **Settings → API Keys** (shown once on create). Recording needs Settings → Recording (or `configure(record=…)` / job metadata) plus agent `LIVEKIT_*` credentials. Org **LiveKit integration** (signing key + API secret) is optional: it enables signed egress webhooks for faster `audio_available` confirmation; without it, recordings still upload to R2 and confirm via lazy R2 reconcile when the session is opened.

Recording policy (precedence: job metadata → `configure(record=…)` → Settings → Recording via bootstrap):

- **UI:** Parlot → Settings → Recording (per-agent toggles + globs for unseen agents)
- **Code:** `configure(record=True)`, `configure(record=False)`, or `configure(record=["my-agent*"])`
- **Dispatch:** job metadata `{ "record": true|false }`

Optional: `PARLOT_CAPTURE_CONTENT=false` to suppress prompt/response text in spans.

Optional: `PARLOT_DIAGNOSTICS=off` to disable SDK self-diagnostics (export/handler failures reported to Parlot). Default is on; metadata only, no conversation content. Under sustained outage the buffer drops and circuit-breaks — it does not retry-storm the collector.

## Examples

- [`examples/livekit-voice`](../../examples/livekit-voice/) — minimal hello-world
- [`examples/multi-agent`](../../examples/multi-agent/) — storytelling handoffs
- [`examples/restaurant-agent`](../../examples/restaurant-agent/) — greeter → specialist routing
- [`examples/hotel-receptionist`](../../examples/hotel-receptionist/) — boutique-hotel receptionist + seed sample sessions

## Development

```bash
uv sync --group dev
uv run pytest -q
```
