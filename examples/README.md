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

## Running examples in this repo

Each example uses editable local path dependencies to `packages/*` so SDK changes are immediately available.

```bash
cd examples/livekit/livekit-voice
uv sync
cp .env.example .env
# Fill in PARLOT_API_KEY (mint in Settings → API Keys) and provider credentials
# PARLOT_ENDPOINT defaults to https://ingest.parlot.ai in .env.example
uv run python agent.py dev
```

## Copying an example into your own project

If you copy an example into a standalone repository or project:

1. Remove the `[tool.uv.sources]` section from `pyproject.toml`.
2. Install Parlot packages from PyPI:

```bash
# Using uv
uv add parlot-instrumentation-livekit

# Or using pip
pip install parlot-instrumentation-livekit
```
