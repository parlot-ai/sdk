# Parlot

**Production voice AI observability** — MIT OpenTelemetry instrumentation for LiveKit Agents (and LangGraph when you already run voice).

Know if your voice agent is actually working. Install the sidecar, call `parlotize()` once, and Parlot models each call as **turns**: timeline, multi-agent handoff graph, pipeline waterfall, and goal completion with an evidence trail to the proving turns and audio.

Works with LiveKit Cloud, self-hosted media, and [LiveKit on Telnyx](https://telnyx.com/products/livekit-on-telnyx).

## Install

```bash
# LiveKit Agents (recommended)
pip install "parlot[livekit]"

# LangGraph / LangChain (same debugger for text agents alongside voice)
pip install "parlot[langgraph]"

# Both
pip install "parlot[all]"
```

Or install an instrumentation package directly:

```bash
pip install parlot-instrumentation-livekit
# or
pip install parlot-instrumentation-langgraph
```

## Instrument (LiveKit)

```python
from parlot.instrumentation.livekit import parlotize

parlotize(agent_id="my-agent")
```

Call `parlotize(agent_id=...)` before constructing `AgentSession`, then `await ctx.connect()` before `session.start()`. Set `PARLOT_ENDPOINT` and `PARLOT_API_KEY` (mint in Settings → API Keys).

Full checklist: [LiveKit guide](https://parlot.ai/docs/guides/livekit) · [Quick Start](https://parlot.ai/docs/quick-start)

## Documentation

[parlot.ai/docs](https://parlot.ai/docs) · [parlot.ai](https://parlot.ai) · [GitHub](https://github.com/parlot-ai/sdk)
