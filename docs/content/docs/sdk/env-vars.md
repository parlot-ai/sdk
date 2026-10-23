---
title: Environment Variables
description: Complete reference of environment variables supported by the Parlot SDK.
sidebar_position: 6
sidebar_custom_props:
  eyebrow: Configuration
---

# Environment Variables Reference

The Parlot SDK can be configured via environment variables or explicitly through `parlotize()` arguments.

## Core telemetry and ingestion

| Variable          | Required  | Default | Description |
| ----------------- | --------- | ------- | ----------- |
| `PARLOT_ENDPOINT` | **Yes\*** | _None_  | Base URL of the Parlot OpenTelemetry Protocol (OTLP) collector (e.g. `https://ingest.parlot.ai`). The SDK appends `/v1/traces` for spans, `/v1/metrics` for metrics (LiveKit), and `/v1/logs` for session application logs. <br/>_\*Required when `endpoint=` is omitted from `parlotize()`._ |
| `PARLOT_API_KEY`  | **Yes\*** | _None_  | Bearer token from Parlot **Settings → API keys**. Required for authenticated ingest, Settings bootstrap, and recording grants. Without it the process can start, but telemetry will not authenticate. |
| `PARLOT_DEBUG_LEVEL` | —      | `INFO`  | Level for **Parlot** loggers only (`parlot.*`, including LiveKit / LangGraph / Pipecat instrumentation). Does **not** raise the process root logger — so `DEBUG` will not flood `websockets` / `aiortc`. Values: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

### Deploy convention (not an SDK env var)

Pass `agent_id` as the first argument to `parlotize()`. A common deploy-manifest pattern is:

```python
parlotize(os.environ["PARLOT_AGENT_ID"])
```

The SDK does not read `PARLOT_AGENT_ID` itself.

---

## Capture policies (no env vars)

Recording, session logs, and generative AI (GenAI) content capture are controlled by:

1. **Job / context metadata** — e.g. LiveKit job metadata `record`, `capture_logs`, `capture_genai_content`
2. **`parlotize(...)` arguments** — `record=`, `capture_logs=`, `capture_genai_content=`
3. **Settings** — **Settings → Recording**, **Settings → Logs**, **Settings → Gen AI content capture** (loaded at bootstrap)
4. **SDK defaults** — capture policies default to **on**

When GenAI content capture is off, message and tool payloads are **omitted**; span structure, timings, token counts, and turn transcripts still export.

See [Concepts → Recording vs telemetry](/sdk/get-started/concepts#recording-vs-telemetry) and [Agent policy allowlists](/app/agent-policy-allowlists).

---

## Framework-specific variables

### LiveKit Agents

When using `parlot-instrumentation-livekit` with LiveKit:

| Variable             | Required | Description |
| -------------------- | -------- | ----------- |
| `LIVEKIT_URL`        | Yes      | WebSocket URL for your LiveKit server (e.g. `wss://my-project.livekit.cloud`). |
| `LIVEKIT_API_KEY`    | Yes      | LiveKit project API key (also used to start Room Composite recordings). |
| `LIVEKIT_API_SECRET` | Yes      | LiveKit project API secret. |
