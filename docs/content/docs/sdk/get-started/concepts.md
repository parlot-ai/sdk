---
title: Concepts
description: What Parlot instruments and how sessions, turns, and agents relate.
sidebar_position: 2
---

# Concepts

## Why Parlot

Parlot models each production voice agent call as sessions and turns, then stores the underlying
OpenTelemetry spans as the lasting record. The platform turns those spans into interaction graphs
and goal evaluations.

## Packages

| Package | Role |
|---------|------|
| `parlot-core` | Semantic conventions (GenAI v1.41 + Conversation Contract + voice), base processor, shared provider helpers |
| `parlot-instrumentation-livekit` | LiveKit Agents OpenTelemetry instrumentation, Room Composite recording hooks, platform refs |
| `parlot-instrumentation-langgraph` | LangGraph / LangChain `parlotize()` via global callbacks |
| `parlot-instrumentation-pipecat` | Pipecat voice agents — Conversation Contract via OpenTelemetry remap |

Contract helpers (`record_human_rep`, `set_session_metadata`, `add_platform_ref`, …) live in
`parlot.core`. Framework packages re-export them for convenience — prefer those re-exports in
agent code. See the [Python API Reference](/sdk/python) and
[Interactive API Docs](/docs/ref/python/).

## Shared span vocabulary

Adapters share a Conversation Contract and OpenTelemetry generative AI (GenAI) semantic
conventions (semconv) v1.41.0. LiveKit also emits voice and handoff spans.

1. **Conversation Contract** — `parlot.session`, `parlot.turn`, `parlot.session.close`
   (LiveKit also emits `parlot.agent.handoff`)
2. **OpenTelemetry GenAI** (semconv v1.41.0) — `invoke_agent`, `chat`, `execute_tool {name}`,
   `invoke_workflow`
3. **Voice** (LiveKit) — `tts`, `stt`, end-of-utterance detection (`eou_detection`),
   answering-machine detection (`amd`)

Framework guides explain how each adapter attaches to this vocabulary — see
[LangGraph](/sdk/guides/langgraph), [LiveKit](/sdk/guides/livekit), and [Pipecat](/sdk/guides/pipecat).

## Session and agent identity

- A **session** is one bounded interaction (a call / job).
- Today LiveKit voice sets `conversation_id` equal to `session_id` (1:1) as a placeholder until
  multi-session conversations are modeled.
- `parlotize("…", version=...)` stamps deployment identity used by the Parlot Agents portfolio.
  **`agent_id` is required.**
- Version: pass `parlotize(version=...)`; if omitted, `gen_ai.agent.version` is `"unknown"`.

Parlot stamps framework-agnostic session attributes on `parlot.session`:

| Attribute | Meaning |
|-----------|---------|
| `session.agent_id` | Canonical deployment identity |
| `session.agent_framework` | Adapter name (e.g. `"livekit"`) |
| `session.agent_framework_raw_id` | Vendor job / run id |
| `session.agent_chain` | Deployment id plus runtime routing |
| `gen_ai.agent.version` | Agent deployment version |

Each framework guide notes how the adapter stamps deployment identity on the live session.

## Recording vs telemetry

- **Telemetry** (turns, handoffs, close, usage) goes over OpenTelemetry Protocol (OTLP) to
  `PARLOT_ENDPOINT` (`/v1/traces`, and `/v1/metrics` where the adapter exports metrics).
- **Audio recording** is framework-specific and **on by default** for new tenants
  (Settings → Recording allowlist `*`). On LiveKit it uses Room Composite egress; opening the
  session in Parlot confirms the audio file is present. Session turns and spans still appear
  while audio confirmation is pending. Turn recording off with an empty allowlist or
  `parlotize(record=False)`.
- **Application logs** capture Python’s `logging` module during an active session (skip
  `print()`) and show on the session **Logs** tab. They export as OTLP logs (`POST /v1/logs`,
  Protocol Buffers) with `session.id` on each record. Policy mirrors recording
  (Settings → Logs + `parlotize(capture_logs=…)`; fallback on). Treat log text as sensitive—it
  may include personally identifiable information (PII).
- **Generative AI content** (LLM/tool bodies) is a separate policy — see
  [Generative AI content capture](#generative-ai-content-capture).

See the [LiveKit guide](/sdk/guides/livekit) for how recording attaches on the agent. Policy and
precedence: [Environment Variables](/sdk/env-vars).

## Generative AI content capture

**GenAI** means generative AI in general—any large language model (LLM) or tool stack.

This policy is shared across adapters (LiveKit, LangGraph, Pipecat, and future frameworks). It controls
whether **message bodies** and **tool request/response payloads** are attached to GenAI spans.

| Mode | Behavior |
|------|----------|
| **On** (default) | Emit generative AI message event bodies and tool input/output payloads |
| **Off** | Omit those bodies; still emit span structure, timings, token/usage metrics, tool names/error flags, and contract turn text (`turn.user_text` / `turn.agent_text`) |

This policy covers message and tool payloads only. Audio recording, session application logs, and
instruction excerpts use their own settings.

Precedence (same ladder as recording/logs; fallback is **on**):

job metadata `capture_genai_content` → `parlotize(capture_genai_content=…)` →
Settings → Gen AI content capture → on

- **UI:** Parlot → **Settings → Gen AI content capture** / agent Settings tab — wildcard
  patterns (default `*`) and per-agent toggles. Empty patterns turn capture off org-wide for new
  agents.
- **Code:** `parlotize(capture_genai_content=True|False)` overrides Settings for the process.
- **Dispatch:** job metadata `{ "capture_genai_content": true|false }` (where the framework
  supports job metadata).

Resolved from Settings when each span is sent, so new jobs pick up per-agent toggles.
Already-running processes keep the policy they loaded until you restart them.

## Human escalation

Human takeover (phone bridge, warm transfer, supervisor join) is a distinct path from AI
sub-agent routing. Internal AI handoffs use normal sub-agents and leave escalation unmarked.
Signal human escalation explicitly.

When a live rep takes over, register them as a `human_rep` participant. Parlot marks the session
as escalated and renders `human_rep` as a distinct participant in the interaction graph.

| Signal | When to use |
|---|---|
| `record_human_rep(participant_id)` | Explicit call when you know the rep identity |
| `human_escalation()` context manager | Wrap a dial/transfer so the **next** participant who joins is stamped automatically |

`agent.transfer.reason=human_escalation` on handoff spans is an optional analytics label for
*why* a transfer happened. Escalation detection uses the explicit signals above.

### Role vocabulary

| `turn.participant_role` | Meaning |
|---|---|
| `user` | Caller / end user |
| `agent` | AI worker |
| `human_rep` | Live human who took over the session |

### Explicit call

```python
from parlot.core import record_human_rep

# Or: from parlot.instrumentation.livekit import record_human_rep
record_human_rep("support_rep_jane", label="Jane")
```

This stamps the rep on the live session as soon as they are registered (including before they
speak) and registers the participant so future turns use `turn.participant_role=human_rep`.

Framework adapters may add auto-detect paths (for example LiveKit SIP warm transfer). See
[LiveKit → Human escalation](/sdk/guides/livekit#human-escalation).

## Custom metadata and external references

Use these helpers to attach your own data to a live Parlot session.

### Custom session metadata

`set_session_metadata` stamps key/value pairs under the reserved `session.metadata.*` namespace.
Values appear on the session in Parlot (Overview → Custom metadata).

```python
from parlot.core import set_session_metadata

# Or: from parlot.instrumentation.livekit import set_session_metadata
set_session_metadata(order_id="12345", crm_ticket="TKT-9")
```

Notes:

- Call after the session has started. Values set with no active session are ignored.
- Keys are normalized to `session.metadata.<name>` — always use that prefix.
- Values are stored as strings. Prefer short identifiers and labels; avoid transcripts or PII
  that should stay out of session attributes.
- Custom metadata applies at the session level today.

For a single key:

```python
from parlot.core import set_session_attribute

set_session_attribute("retry_count", 2)
```

### External references (searchable IDs)

`add_platform_ref` attaches a searchable external ID to the session (for example a CRM ticket or
your own call ID). Paste that value into Parlot session search / resolve to open the matching
session.

```python
from parlot.core import add_platform_ref

# Or: from parlot.instrumentation.livekit import add_platform_ref
add_platform_ref("crm_ticket", "TKT-9")
```

Framework adapters stamp their own room / job IDs as `platform.ref.*` during session start. Use
`add_platform_ref` for your own identifiers. Optional `framework=` defaults to `"custom"`:

```python
add_platform_ref("order_id", "ORD-100", framework="shopify")
```

## Errors in the session waterfall

Failed LLM and tool work is surfaced at ingest. Turn-level `has_error` in session detail is
derived at query time from child operational spans under that turn’s `trace_id`.

Fix provider credentials or tool logic locally; Parlot shows the failed span in the Timeline
stage chart (waterfall) after OTLP data arrives.
