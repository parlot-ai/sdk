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

Each example depends on published Parlot packages from PyPI (`parlot[livekit]` or `parlot[langgraph]`).

Requires [uv](https://docs.astral.sh/uv/) and the [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/) (`lk`) for local agent dev/console.

```bash
cd examples/livekit/livekit-voice
uv sync
cp .env.example .env
# Fill in PARLOT_API_KEY (mint in Settings → API Keys) and provider credentials
# PARLOT_ENDPOINT defaults to https://ingest.parlot.ai in .env.example
lk agent dev
```

## Copying an example into your own project

Examples already install Parlot from PyPI. To add the same dependency in your own project:

```bash
# Using uv (LiveKit)
uv add "parlot[livekit]"

# Or using pip
pip install "parlot[livekit]"
```
