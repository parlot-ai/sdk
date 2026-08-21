# Parlot SDK Examples

This directory contains reference implementations of AI agents instrumented with Parlot OpenTelemetry observability.

## Examples Overview

| Directory | Framework | Description |
| --- | --- | --- |
| `livekit/livekit-voice` | LiveKit Agents | Minimal voice assistant with STT, LLM, TTS |
| `livekit/healthcare` | LiveKit Agents | Patient appointment triage and doctor escalation |
| `livekit/hotel-receptionist` | LiveKit Agents | Multi-tool hotel concierge with complex business policies |
| `livekit/drive-thru` | LiveKit Agents | Fast-food ordering agent |
| `livekit/restaurant-agent` | LiveKit Agents | Restaurant booking and multi-agent routing |
| `livekit/multi-agent` | LiveKit Agents | Multi-agent handoff orchestration |
| `langgraph/minimal-agent` | LangGraph | Graph-based conversational agent with callback telemetry |

## Running Examples Locally (Monorepo Development)

Each example uses editable local path dependencies to `packages/*` so SDK changes are immediately available.

```bash
cd examples/livekit/livekit-voice
uv sync
cp .env.example .env
# Fill in your PARLOT_API_KEY and provider credentials
uv run python agent.py dev
```

## Using Examples Outside the Monorepo

If you copy an example into your own standalone repository or project:

1. Remove the `[tool.uv.sources]` section from `pyproject.toml`.
2. Install Parlot packages directly from PyPI:

```bash
# Using uv
uv add parlot-instrumentation-livekit

# Or using pip
pip install parlot-instrumentation-livekit
```
