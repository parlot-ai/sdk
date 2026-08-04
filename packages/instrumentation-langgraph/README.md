# parlot-instrumentation-langgraph

OpenTelemetry instrumentation for LangGraph / LangChain agents.

```python
from parlot.instrumentation.langgraph import configure

configure(agent_id="support-bot", version="0.1.0", channel="webchat")

# Normal LangGraph usage — no per-call callbacks required
graph.invoke(
    {"messages": [("user", "Hello")]},
    config={"configurable": {"thread_id": "demo-1"}},
)
```

If `thread_id` is not provided, Parlot mints one automatically (`anon-…`) so
contract spans still attach to a session.

Pass `channel` (e.g. `webchat`, `sms`) when LangGraph owns the session so
ingest does not assume voice. Optional `modality` overrides the default
derived from channel (`webchat`/`sms`/`whatsapp` → text, `voice` → voice).

Set `PARLOT_ENDPOINT` and `PARLOT_API_KEY`. Optional: `PARLOT_CAPTURE_CONTENT=false`.

When used inside a LiveKit voice agent that already called
`parlot.instrumentation.livekit.configure()`, this package nests GenAI
operational spans under the active LiveKit session and does **not** emit
duplicate `parlot.session` / `parlot.turn` spans — LiveKit owns channel and
modality.
