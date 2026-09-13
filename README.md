# Parlot SDK

**Production voice AI observability** for teams shipping LiveKit Agents.

Know if your voice agent is actually working — not just that the pipeline returned 200s. This MIT Python SDK is a thin `parlotize()` sidecar: call it once at startup and Parlot models each call as **turns**, not flat traces. You get a turn timeline, multi-agent handoff graph, and goal completion with a clickable evidence trail to the proving turns and audio.

Works with LiveKit Cloud, self-hosted media, and [LiveKit on Telnyx](https://telnyx.com/products/livekit-on-telnyx).

**Docs:** [parlot.ai/docs](https://parlot.ai/docs) · **Product:** [parlot.ai](https://parlot.ai)

## The questions production voice teams ask

| | |
|---|---|
| **Did the call work?** | Goal completion in business language (booked, resolved, paid) — with an evidence trail to the turns and audio, not a score beside a separate debugger. |
| **Which agent broke it?** | Greeter → specialist → checkout: the multi-agent handoff graph and cascading-failure attribution. |
| **Agent failure or audio failure?** | Full turn waterfall (STT / LLM / TTS / end-to-end) correlated with optional call audio. |

## Install (LiveKit)

```bash
# Using pip
pip install parlot-instrumentation-livekit

# Or with uv
uv add parlot-instrumentation-livekit

# Or via the parlot meta-package
pip install "parlot[livekit]"
```

## Instrument

Call `parlotize()` before constructing `AgentSession`, then `await ctx.connect()` before `session.start()`:

```python
from parlot.instrumentation.livekit import parlotize

parlotize()

from livekit.agents import AgentSession, JobContext, WorkerOptions, cli


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(...)
    await session.start(agent=..., room=ctx.room)
```

```bash
export PARLOT_ENDPOINT=https://ingest.parlot.ai
export PARLOT_API_KEY=<org-scoped-key>
```

Mint the API key in Parlot **Settings → API Keys**. Full checklist (recording, version, refs): [instrumentation-livekit README](packages/instrumentation-livekit/README.md#integration-checklist). Guides: [parlot.ai/docs](https://parlot.ai/docs).

## What the sidecar captures

- **LiveKit-native** — AgentSession lifecycle and pipeline spans (STT / LLM / TTS / tools), including fully self-hosted media where [LiveKit Agent Insights](https://docs.livekit.io/deploy/observability/insights/) does not run.
- **Conversational turns** — caller, AI agents, and human reps as first-class turns on one timeline.
- **Graph + waterfall** — handoffs with edge latency; STT / LLM TTFT / TTS / end-to-end timing per turn.
- **Optional recording** — egress to object storage when enabled in Settings or `parlotize(record=…)`.
- **OTLP-native and removable** — standard export; remove `parlotize()` and the agent still works.

## Examples

| Example | Description |
|---------|-------------|
| [`examples/livekit/livekit-voice/`](examples/livekit/livekit-voice/) | Minimal hello-world LiveKit agent |
| [`examples/livekit/multi-agent/`](examples/livekit/multi-agent/) | Storytelling handoffs (graph demo) |
| [`examples/livekit/restaurant-agent/`](examples/livekit/restaurant-agent/) | Greeter → specialist routing |
| [`examples/livekit/hotel-receptionist/`](examples/livekit/hotel-receptionist/) | Boutique-hotel receptionist + persona sessions |
| [`examples/livekit/healthcare/`](examples/livekit/healthcare/) | Front desk (intake, appointments, billing) + persona sims |
| [`examples/livekit/drive-thru/`](examples/livekit/drive-thru/) | Ordering with dynamic tools + persona sims |
| [`examples/livekit/persona_sim/`](examples/livekit/persona_sim/) | Shared persona-LLM text session driver |
| [`examples/langgraph/minimal-agent/`](examples/langgraph/minimal-agent/) | Standalone LangGraph + `parlotize()` |

## LangGraph / text agents

Already running voice **and** LangGraph / LangChain? Keep one debugger — same turn model for calls and background agent runs. Install `parlot-instrumentation-langgraph` (or `pip install "parlot[langgraph]"`) and call `parlotize()`; see the [instrumentation-langgraph README](packages/instrumentation-langgraph/README.md).

## License

Instrumentation packages in this repo are **[MIT](LICENSE)**. The companion analysis platform is **BSL 1.1**: free production use up to 4,000 turns/month for your own agents and agents you operate for clients; above that, or to offer Parlot as a hosted service, requires a commercial license. Each version converts to Apache 2.0 four years after its first public release. Enterprise governance features require an EE license key.

## Development

```bash
uv sync --group dev
uv run pytest -q
```

Use `uv run` from the repo root rather than `pip install` / bare `python -m pytest`.

**Packages:** `packages/meta/` (`parlot` meta-package) · `packages/core/` (semantic conventions, base processor) · `packages/instrumentation-livekit/` · `packages/instrumentation-langgraph/`

**Contributing / releases:** [CONTRIBUTING.md](CONTRIBUTING.md) (PR-only `main`, conventional PR titles, Release Please).

### Agent Deployment Version

Parlot stamps `gen_ai.agent.version` on each session from `parlotize(version=...)`. If you omit `version=` (or pass blank), the attribute is `"unknown"`.

```python
parlotize(agent_id="restaurant-agent", version="0.1.0")
```

This powers version tracking on the Agents portfolio and per-session attributes in the platform UI.

### Send telemetry to Parlot

Point the agent at the hosted OTLP collector (no path suffix — the SDK appends `/v1/traces` and `/v1/metrics`):

```bash
export PARLOT_ENDPOINT=https://ingest.parlot.ai
export PARLOT_API_KEY=<org key from Settings → API Keys>
```
