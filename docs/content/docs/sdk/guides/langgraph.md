---
title: LangGraph instrumentation
description: parlotize() for LangGraph / LangChain agents.
sidebar_position: 3
sidebar_custom_props:
  eyebrow: LangGraph
---

# LangGraph instrumentation

`parlot-instrumentation-langgraph` registers a global LangChain callback handler
via LangChain’s `register_configure_hook` / `CallbackManager.configure` injection
so every `invoke` / `ainvoke` / `astream` emits Parlot Conversation Contract
spans plus OTel GenAI operational spans.

## Quick start

```python
from parlot.instrumentation.langgraph import parlotize, close_session

parlotize("support-bot", version="0.1.0")

graph.invoke(
    {"messages": [("user", "Hello")]},
    config={"configurable": {"thread_id": "demo-1"}},
)

close_session("demo-1")  # optional; also flushed on process exit
```

Environment: `PARLOT_ENDPOINT`, `PARLOT_API_KEY` — see [Environment Variables](/sdk/env-vars).
Shared `parlotize()` options: [Python SDK Reference](/sdk/python). LangGraph-only
kwargs (`channel`, `modality`) and `close_session`: [Interactive API Reference](/docs/ref/python/parlot/instrumentation/langgraph.html).

For standalone (non-LiveKit) sessions, set `channel=` (e.g. `"webchat"`) and
optionally `modality=` so ingest does not assume voice:

```python
parlotize("support-bot", version="0.1.0", channel="webchat", modality="text")
```

Generative AI content capture is shared across adapters — see
[Concepts → Generative AI content capture](/sdk/get-started/concepts#generative-ai-content-capture).
Override for the process with `parlotize(capture_genai_content=False)`.

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
from parlot.instrumentation.livekit import parlotize as parlotize_livekit
from parlot.instrumentation.langgraph import parlotize as parlotize_langgraph

parlotize_livekit("voice-bot", version="0.1.0")
parlotize_langgraph("voice-bot")  # adopts LiveKit TracerProvider when already set
```

- LiveKit owns `parlot.session` / `parlot.turn` (voice).
- LangGraph emits nested GenAI ops (`chat`, `execute_tool`, `invoke_workflow`) under the active OTel context (LiveKit’s remapped `chat` span).
- No duplicate contract spans.
