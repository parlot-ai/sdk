# Minimal LangGraph agent (Parlot)

Standalone text agent that calls `parlot.instrumentation.langgraph.parlotize()`
and runs a tiny StateGraph with one tool.

## Setup

```bash
cd examples/langgraph/minimal-agent
uv sync
export PARLOT_ENDPOINT=https://ingest.parlot.ai
export PARLOT_API_KEY=...
# Optional model (defaults to a fake echo LLM if OPENAI_API_KEY is unset)
export OPENAI_API_KEY=...
```

## Run

```bash
uv run python agent.py
```

## Expected spans

| Span | Source |
|------|--------|
| `parlot.session` | First invoke for `thread_id` |
| `parlot.turn` | Per root graph run (user + agent) |
| `invoke_agent` | Root graph chain |
| `invoke_workflow` | Intermediate nodes |
| `chat` / `chat {model}` | LLM calls |
| `execute_tool lookup_time` | Tool calls |
| `parlot.session.close` | Explicit `close_session` / process exit |

No LiveKit dependency — proves text-modality instrumentation alone.
