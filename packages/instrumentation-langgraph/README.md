# parlot-instrumentation-langgraph

Parlot’s lead product is production voice observability on LiveKit. Use this package when you already run voice and want the **same debugger** for LangGraph / LangChain — same turn model, not a separate product.

Prefer [`parlot-instrumentation-livekit`](https://pypi.org/project/parlot-instrumentation-livekit/) for voice agents.

**Docs:** [LangGraph guide](https://parlot.ai/docs/guides/langgraph) · [Quick Start](https://parlot.ai/docs/sdk/get-started/quick-start) · [parlot.ai](https://parlot.ai)

## Install

```bash
pip install parlot-instrumentation-langgraph
# or: uv add parlot-instrumentation-langgraph
# or: pip install "parlot[langgraph]"
```

## Instrument

```python
from parlot.instrumentation.langgraph import parlotize

parlotize("support-bot", version="0.1.0", channel="webchat")

# Normal LangGraph usage — no per-call callbacks required
graph.invoke(
    {"messages": [("user", "Hello")]},
    config={"configurable": {"thread_id": "demo-1"}},
)
```

Pass `channel` (e.g. `webchat`, `sms`) when LangGraph owns the session. If `thread_id` is omitted, Parlot mints one automatically. When used inside a LiveKit agent that already called LiveKit `parlotize()`, this nests GenAI spans under that session — see the [LangGraph guide](https://parlot.ai/docs/guides/langgraph).

## Configure

```bash
export PARLOT_ENDPOINT=https://ingest.parlot.ai
export PARLOT_API_KEY=<org-scoped-key>
```

Mint the API key in Parlot **Settings → API Keys**. Session logs and generative AI content capture are configured in Settings or via `parlotize(...)` kwargs — see the [LangGraph guide](https://parlot.ai/docs/guides/langgraph).

## Next

- [LangGraph guide](https://parlot.ai/docs/guides/langgraph)
- [Concepts](https://parlot.ai/docs/concepts)
- Example: [`examples/langgraph/minimal-agent/`](../../examples/langgraph/minimal-agent/)
