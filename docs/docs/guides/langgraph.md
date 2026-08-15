---
title: LangGraph instrumentation
description: configure() for LangGraph / LangChain agents.
sidebar_position: 3
---

# LangGraph instrumentation

`parlot-instrumentation-langgraph` registers a global LangChain callback handler
via LangChain’s `register_configure_hook` / `CallbackManager.configure` injection
so every `invoke` / `ainvoke` / `astream` emits Parlot Conversation Contract
spans plus OTel GenAI operational spans.

## Quick start

```python
from parlot.instrumentation.langgraph import configure, close_session

configure(agent_id="support-bot", version="0.1.0")

graph.invoke(
    {"messages": [("user", "Hello")]},
    config={"configurable": {"thread_id": "demo-1"}},
)

close_session("demo-1")  # optional; also flushed on process exit
```

Environment: `PARLOT_ENDPOINT`, `PARLOT_API_KEY`.

Content capture (GenAI message bodies and tool payloads; default on) follows
Settings → Content via telemetry bootstrap, or `configure(capture_content=False)`
to override for the process. Does not gate contract turn text.

See [`examples/langgraph/minimal-agent`](https://github.com/parlot-ai/sdk/tree/main/examples/langgraph/minimal-agent).

## Span vocabulary

| Layer | Spans |
|-------|-------|
| Contract | `parlot.session`, `parlot.turn`, `parlot.session.close` |
| GenAI (semconv v1.41) | `invoke_agent`, `invoke_workflow`, `chat` / `chat {model}`, `execute_tool {name}` |

Session key is LangGraph `thread_id` (`session.modality=text`). If `thread_id`
is omitted, Parlot mints one automatically (`anon-…`) for the process lifetime.

## LiveKit + LangGraph

When a LiveKit voice agent uses `livekit.plugins.langchain.LLMAdapter`, call **both**:

```python
from parlot.instrumentation.livekit import configure as configure_livekit
from parlot.instrumentation.langgraph import configure as configure_langgraph

configure_livekit(agent_id="voice-bot", version="0.1.0")
configure_langgraph()  # adopts LiveKit TracerProvider when already set
```

- LiveKit owns `parlot.session` / `parlot.turn` (voice).
- LangGraph emits nested GenAI ops (`chat`, `execute_tool`, `invoke_workflow`) under the active OTel context (LiveKit’s remapped `chat` span).
- No duplicate contract spans.
