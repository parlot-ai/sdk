---
title: Environment Variables
description: Complete reference of environment variables supported by the Parlot SDK.
sidebar_position: 6
sidebar_custom_props:
  eyebrow: Configuration
---

# Environment Variables Reference

The Parlot SDK can be configured via environment variables or explicitly through `parlotize()` arguments.

## Core Telemetry & Ingestion

| Variable               | Required  | Default   | Description                                                                                                                                                                                                                                |
| ---------------------- | --------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `PARLOT_ENDPOINT`      | **Yes\*** | _None_    | Base URL of the Parlot OTLP collector (e.g. `https://ingest.parlot.ai`). Spans are exported to `{PARLOT_ENDPOINT}/v1/traces`. <br/>_\*Required unless `endpoint=` is passed to `parlotize()`._ |
| `PARLOT_API_KEY`       | **Yes**   | _None_    | Bearer authentication token minted under Parlot **Settings → API Keys**.                                                                                                                                                                   |
| `PARLOT_AGENT_ID`      | Optional  | _Derived_ | Canonical deployment identifier stamped on `session.agent_id`. In LiveKit, defaults to `WorkerOptions.agent_name` or `parlotize(agent_id=...)`.                                                                                            |

---

## Policies & Capture Controls

| Variable                       | Default | Values                                    | Description                                                                                                                                                                                                                                           |
| ------------------------------ | ------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PARLOT_CAPTURE_GENAI_CONTENT` | `true`  | `true` \| `false` \| `1` \| `0`           | Controls whether LLM message bodies and tool input/output payloads are exported with GenAI spans. If `false`, payloads are redacted while preserving span metrics, token counts, and turn transcripts.                                                |
| `PARLOT_DEBUG_LEVEL`           | `INFO`  | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | Sets root logging level for internal SDK loggers (`parlot.core`, `parlot.instrumentation.livekit`, `parlot.instrumentation.langgraph`).                                                                                                               |

---

## Framework-Specific Variables

### LiveKit Agents

When using `parlot-instrumentation-livekit` with LiveKit:

| Variable             | Required | Description                                                                    |
| -------------------- | -------- | ------------------------------------------------------------------------------ |
| `LIVEKIT_URL`        | Yes      | WebSocket URL for your LiveKit server (e.g. `wss://my-project.livekit.cloud`). |
| `LIVEKIT_API_KEY`    | Yes      | LiveKit project API key (also used to initiate egress recordings).             |
| `LIVEKIT_API_SECRET` | Yes      | LiveKit project API secret.                                                    |

---

## Configuration Precedence

When both environment variables and programmatic arguments are provided, the resolution precedence is:

1. **Job / Context Metadata:** Dispatched parameters (e.g. LiveKit job metadata `record: true`, `capture_genai_content: false`).
2. **Programmatic Arguments:** Arguments explicitly passed to `parlotize(...)`.
3. **Environment Variables:** `PARLOT_*` environment variables.
4. **Remote Telemetry Bootstrap:** Dynamic policies configured in the Parlot Web UI (**Settings → Recording**, **Settings → Logs**, **Settings → Generative AI**).
5. **SDK Built-in Defaults:** (e.g. GenAI content capture is on by default, session logging is on by default).
