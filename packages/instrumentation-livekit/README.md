# parlot-instrumentation-livekit

MIT OpenTelemetry instrumentation for **[LiveKit Agents](https://docs.livekit.io/agents/)** — the primary path into [Parlot](https://parlot.ai), the observability platform for **production voice AI**.

Know if your voice agent is actually working: conversational **turns** (not flat traces), multi-agent handoff graph, STT / LLM / TTS waterfall, optional call recording, and goal completion with an evidence trail to the proving turns and audio.

Works with LiveKit Cloud, fully self-hosted media, and [LiveKit on Telnyx](https://telnyx.com/products/livekit-on-telnyx).

```bash
pip install parlot-instrumentation-livekit
# or: uv add parlot-instrumentation-livekit
# or: pip install "parlot[livekit]"
```

```python
from parlot.instrumentation.livekit import parlotize

parlotize("my-agent")
```

**Docs:** [LiveKit guide](https://parlot.ai/docs/guides/livekit) · [Concepts](https://parlot.ai/docs/concepts) · [Quick Start](https://parlot.ai/docs/quick-start) · [parlot.ai](https://parlot.ai)

## Integration checklist

Two steps are required for full Parlot behavior. All SDK examples follow this pattern.

### 1. `parlotize()` at import (required)

Call before constructing `AgentSession` — patches `AgentSession.__init__`, sets up OTLP export to `PARLOT_ENDPOINT`, and installs turn/handoff/close event hooks.

```python
from parlot.instrumentation.livekit import parlotize

parlotize("my-agent")
```

`agent_id` is a required positional argument for canonical deployment identity. Pass `version=` for deployment version.

#### What to expect for version

Pass `parlotize(version=...)` to stamp a deployment version on `gen_ai.agent.version`. If omitted (or blank), Parlot stamps `"unknown"`.

```python
parlotize("restaurant-agent", version="0.1.0")
```

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

Set `PARLOT_ENDPOINT` and `PARLOT_API_KEY`. The API key is **org-scoped** — mint it in Parlot **Settings → API Keys** (shown once on create). Recording needs Settings → Recording (or `parlotize(record=…)` / job metadata) plus agent `LIVEKIT_*` credentials. Recordings upload to R2 and confirm via lazy R2 reconcile when the session is opened.

Recording policy (precedence: job metadata → `parlotize(record=…)` → Settings → Recording via bootstrap):

- **UI:** Parlot → Settings → Recording (per-agent toggles + globs for unseen agents)
- **Code:** `parlotize(record=True)`, `parlotize(record=False)`, or `parlotize(record=["my-agent*"])`
- **Dispatch:** job metadata `{ "record": true|false }`

Session application logs (Python `logging`, default on) use the same control path via Settings → Logs / `parlotize(capture_logs=…)` / job `capture_logs`. Not `print()`. Treat content like stdout for PII.

Generative AI content capture (message bodies / tool payloads; default on) is documented in [Concepts](https://parlot.ai/docs/concepts#generative-ai-content-capture). Override with `parlotize(capture_genai_content=True|False)`.

## Examples

- [`examples/livekit/livekit-voice`](../../examples/livekit/livekit-voice/) — minimal hello-world
- [`examples/livekit/multi-agent`](../../examples/livekit/multi-agent/) — storytelling handoffs (graph demo)
- [`examples/livekit/restaurant-agent`](../../examples/livekit/restaurant-agent/) — greeter → specialist routing
- [`examples/livekit/hotel-receptionist`](../../examples/livekit/hotel-receptionist/) — boutique-hotel receptionist + seed sample sessions

## Development

```bash
uv sync --group dev
uv run pytest -q
```
