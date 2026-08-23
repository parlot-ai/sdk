---
title: LangGraph API
description: API reference for parlot-instrumentation-langgraph.
sidebar_position: 3
---

# LangGraph API Reference

`parlot-instrumentation-langgraph` provides OpenTelemetry instrumentation for LangGraph and LangChain agents. It registers a global callback handler so that all graph invocations emit Parlot Conversation Contract spans and OTel GenAI (v1.41.0) spans automatically.

## Installation

```bash
# Using pip
pip install parlot-instrumentation-langgraph
# or with meta-package:
pip install "parlot[langgraph]"

# Using uv
uv add parlot-instrumentation-langgraph
```

## Module: `parlot.instrumentation.langgraph`

### `configure()`

```python
def configure(
    *,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_genai_content: Optional[bool] = None,
    service_name: Optional[str] = None,
    tracer_provider: Optional[TracerProvider] = None,
    agent_id: Optional[str] = None,
    version: Optional[str] = None,
    channel: Optional[str] = None,
    modality: Optional[str] = None,
    capture_logs: bool | list[str] | None = None,
    log_level: Optional[str] = None,
) -> None
```

Configures Parlot LangGraph instrumentation, registers the LangChain configure hook (`register_configure_hook`), and sets up OTLP span export.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `endpoint` | `str \| None` | `None` | Parlot OTLP collector base URL (e.g. `https://ingest.parlot.ai`). If omitted, reads `PARLOT_ENDPOINT`. |
| `api_key` | `str \| None` | `None` | Org API key minted in Parlot **Settings → API Keys**. If omitted, reads `PARLOT_API_KEY`. |
| `agent_id` | `str \| None` | `None` | Canonical agent deployment ID stamped on `session.agent_id`. |
| `version` | `str \| None` | `None` | Deployment version stamped on `gen_ai.agent.version`. Precedence: `version=` kwarg → `__main__.__version__` → `PARLOT_AGENT_VERSION` → local git SHA (dev only). |
| `channel` | `str \| None` | `None` | Communication channel for standalone LangGraph sessions (e.g. `"webchat"`, `"slack"`, `"sms"`). Defaults to `"text"`. When running inside LiveKit, channel is managed by LiveKit. |
| `modality` | `str \| None` | `None` | Session interaction modality (`"text"`, `"voice"`, or `"multimodal"`). Defaults to `"text"` for standalone LangGraph sessions. |
| `capture_genai_content` | `bool \| None` | `None` | Process-wide override for LLM message bodies and tool input/output payloads. If `False`, payloads are omitted while keeping span structure, timings, token usage, and turn texts. Precedence: `capture_genai_content=` kwarg > Parlot Settings → Generative AI (default: on). |
| `capture_logs` | `bool \| list[str] \| None` | `None` | Intercept Python `logging` during active sessions and stream to the session Logs tab. Can be a boolean or glob patterns. Precedence: `capture_logs=` kwarg > Parlot Settings → Logs (default: on). |
| `log_level` | `str \| None` | `None` | Minimum log level for session log capture (e.g. `"INFO"`, `"WARNING"`). Defaults to `"INFO"`. |
| `service_name` | `str \| None` | `None` | OpenTelemetry resource `service.name`. Defaults to `agent_id` or `"langgraph-agent"`. |
| `tracer_provider` | `TracerProvider \| None` | `None` | Existing custom OpenTelemetry `TracerProvider`. If LiveKit has already initialized a tracer provider in the same process, `configure()` automatically adopts it. |

#### Example

```python
from parlot.instrumentation.langgraph import configure

configure(
    agent_id="customer-support-graph",
    version="2.1.0",
    channel="webchat",
    modality="text",
)
```

---

### `close_session()`

```python
def close_session(thread_id: str, *, reason: str = "completed") -> None
```

Explicitly closes a LangGraph-owned session identified by its `thread_id`, emitting the `parlot.session.close` span with accumulated usage tokens, cost, and turn counts.

#### Parameters

- `thread_id` (`str`): The LangGraph thread identifier (`config={"configurable": {"thread_id": "..."}}`).
- `reason` (`str`, optional): Close reason stamped on `session.close_reason`. Defaults to `"completed"`.

#### Example

```python
from parlot.instrumentation.langgraph import configure, close_session

configure(agent_id="support-bot")

# Execute graph invocation
graph.invoke(
    {"messages": [("user", "What is my balance?")]},
    config={"configurable": {"thread_id": "session-xyz"}},
)

# Explicitly close the session when conversation finishes
close_session("session-xyz", reason="completed")
```

---

### `ParlotLangGraphCallbackHandler`

```python
from parlot.instrumentation.langgraph import ParlotLangGraphCallbackHandler
```

A LangChain `BaseCallbackHandler` implementation that translates LangGraph / LangChain execution events (LLM starts/ends, tool invocations, chain runs) into OpenTelemetry GenAI spans (`invoke_agent`, `invoke_workflow`, `chat`, `execute_tool`).

`configure()` automatically registers this handler using LangChain's configuration hooks, so manual attachment to `callbacks=[...]` is not required.

---

## LiveKit + LangGraph Coexistence

When using LangGraph inside a LiveKit voice agent (via `livekit.plugins.langchain.LLMAdapter`), initialize both adapters:

```python
from parlot.instrumentation.livekit import configure as configure_livekit
from parlot.instrumentation.langgraph import configure as configure_langgraph

# 1. LiveKit configuration initializes the main tracer provider
configure_livekit(agent_id="voice-bot", version="1.0.0")

# 2. LangGraph configuration automatically adopts the active TracerProvider
configure_langgraph()
```

- **Contract ownership:** LiveKit owns `parlot.session`, `parlot.turn`, and audio recording.
- **Nested GenAI spans:** LangGraph emits granular LLM and tool spans nested cleanly beneath LiveKit's turn context.
- **Zero span duplication:** LangGraph suppresses redundant session/turn contract spans when LiveKit is active.

---

## Re-exported Core Functions

`parlot.instrumentation.langgraph` re-exports common session helpers from `parlot-core`:

- [`set_session_metadata(**pairs)`](./core.md#set_session_metadata)
- [`set_session_attribute(key, value)`](./core.md#set_session_attribute)
- [`add_platform_ref(kind, value, framework="custom")`](./core.md#add_platform_ref)
- [`stamp_platform_refs(span, refs)`](./core.md#stamp_platform_refs)
- [`record_human_rep(participant_id, label=None)`](./core.md#record_human_rep)
- [`human_escalation(label=None)`](./core.md#human_escalation)
