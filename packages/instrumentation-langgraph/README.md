# parlot-instrumentation-langgraph

OpenTelemetry instrumentation for LangGraph / LangChain agents.

```python
from parlot.instrumentation.langgraph import configure

configure(agent_id="support-bot", version="0.1.0")

# Normal LangGraph usage — no per-call callbacks required
graph.invoke(
    {"messages": [("user", "Hello")]},
    config={"configurable": {"thread_id": "demo-1"}},
)
```

If `thread_id` is not provided, Parlot mints one automatically (`anon-…`) so
contract spans still attach to a session.

Set `PARLOT_ENDPOINT` and `PARLOT_API_KEY`. Optional: `PARLOT_CAPTURE_CONTENT=false`.

When used inside a LiveKit voice agent that already called
`parlot.instrumentation.livekit.configure()`, this package nests GenAI
operational spans under the active LiveKit session and does **not** emit
duplicate `parlot.session` / `parlot.turn` spans.
