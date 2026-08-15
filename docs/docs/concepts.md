---
title: Concepts
description: What Parlot instruments and how sessions, turns, and agents relate.
sidebar_position: 2
---

# Concepts

## Why Parlot

Parlot treats production voice agents as **event systems** first and traces second. OpenTelemetry spans are the durable audit log. The platform turns those spans into sessions, turns, interaction graphs, and goal evaluations.

## Packages

| Package | Role |
|---------|------|
| `parlot-core` | Semantic conventions (GenAI v1.41 + Conversation Contract + voice), base processor, shared provider helpers |
| `parlot-instrumentation-livekit` | LiveKit Agents OTel instrumentation, egress hooks, platform refs |
| `parlot-instrumentation-langgraph` | LangGraph / LangChain `configure()` via global callbacks |

Contract helpers (`record_human_rep`, `set_session_metadata`, `add_platform_ref`, …) live in `parlot.core`. Framework packages re-export them for convenience — prefer those re-exports in agent code.

## Shared span vocabulary

All adapters export the same three layers:

1. **Conversation Contract** — `parlot.session`, `parlot.turn`, `parlot.session.close`, `parlot.agent.handoff`
2. **OTel GenAI** (semconv v1.41.0) — `invoke_agent`, `chat`, `execute_tool {name}`, `invoke_workflow`
3. **Voice** — `tts`, `stt`, `eou_detection`, `amd`

Vendor span and attribute maps live in each framework guide. See [LangGraph](./guides/langgraph.md) and [LiveKit](./guides/livekit.md).

## Session and agent identity

- A **session** is one bounded interaction (a call / job).
- Today LiveKit voice sets `conversation_id` equal to `session_id` (1:1) as a placeholder until multi-session conversations are modeled.
- `configure(agent_id=..., version=...)` stamps deployment identity used by the Parlot Agents portfolio.
- Version resolution order: `configure(version=)` → `__main__.__version__` → `PARLOT_AGENT_VERSION` → local git SHA (dev only).

Parlot stamps framework-agnostic session attributes on `parlot.session`:

| Attribute | Meaning |
|-----------|---------|
| `session.agent_id` | Canonical deployment identity |
| `session.agent_framework` | Adapter name (e.g. `"livekit"`) |
| `session.agent_framework_raw_id` | Vendor job / run id |
| `session.agent_chain` | Deployment id plus runtime routing |
| `gen_ai.agent.version` | Agent deployment version |

Each framework guide documents how those attributes are sourced from the vendor runtime.

## Recording vs telemetry

- **Telemetry** (turns, handoffs, close, usage) always goes over OTLP to `PARLOT_ENDPOINT`.
- **Audio recording** is optional and framework-specific. On LiveKit it uses Room Composite Egress to R2; webhooks confirm upload. Telemetry does not depend on webhooks.
- **Application logs** (Python `logging` only — not `print()`) are captured on by default during an active session and shown on the session **Logs** tab. Policy mirrors recording (Settings → Logs + `configure(capture_logs=…)`), except the fallback is on. Treat log content like stdout for PII.
- **Generative AI content** (LLM/tool bodies) is a separate policy — see [Generative AI content capture](#generative-ai-content-capture).

See the [LiveKit guide](./guides/livekit.md) for egress, policy, and troubleshooting.

## Generative AI content capture

**GenAI** here means generative AI in general (any LLM/tool stack), not a specific vendor.

This policy is shared across adapters (LiveKit, LangGraph, and future frameworks). It controls whether **message bodies** and **tool request/response payloads** are attached to GenAI spans.

| Mode | Behavior |
|------|----------|
| **On** (default) | Emit generative AI message event bodies and tool input/output payloads |
| **Off** | Omit those bodies; still emit span structure, timings, token/usage metrics, tool names/error flags, and contract turn text (`turn.user_text` / `turn.agent_text`) |

Not in scope: audio recording, session application logs, or instruction excerpts.

Precedence (same ladder as recording/logs; fallback is **on**):

job metadata `capture_genai_content` → `configure(capture_genai_content=…)` → Settings → Generative AI (bootstrap) → on

- **UI:** Parlot → **Settings → Generative AI** / agent Settings tab — globs (default `*`) and per-agent toggles. Empty globs turns capture off org-wide for new agents.
- **Code:** `configure(capture_genai_content=True|False)` overrides bootstrap for the process.
- **Dispatch:** job metadata `{ "capture_genai_content": true|false }` (where the framework supports job metadata).

Resolved at span emit time from bootstrap so per-agent Settings toggles apply; restart is not required for new jobs after Settings changes (already-running processes keep their bootstrap cache until restart).

## Human escalation

Human takeover (SIP bridge, warm transfer, supervisor barge-in) is **not** the same as AI sub-agent routing. Internal AI handoffs use normal sub-agents and do **not** mark a session escalated. Human escalation must be signaled explicitly.

When a live rep takes over, register them as a `human_rep` participant. Parlot marks the session as escalated and renders `human_rep` as a distinct participant in the interaction graph.

| Signal | When to use |
|---|---|
| `record_human_rep(participant_id)` | Explicit call when you know the rep identity |
| `human_escalation()` context manager | Wrap a dial/transfer so the **next** participant who joins is stamped automatically |

`agent.transfer.reason=human_escalation` on handoff spans is an optional analytics signal for **why** a transfer happened. It is **not** used for escalation detection today.

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

This stamps the rep on the live session (works even if the rep never speaks) and registers the participant so future turns use `turn.participant_role=human_rep`.

Framework adapters may add auto-detect paths (for example LiveKit SIP warm transfer). See [LiveKit → Human escalation](./guides/livekit.md#human-escalation).

## Custom metadata and external references

Use these helpers to attach your own data to a live Parlot session.

### Custom session metadata

`set_session_metadata` stamps key/value pairs under the reserved `session.metadata.*` namespace. Values appear on the session in Parlot (Overview → Custom metadata).

```python
from parlot.core import set_session_metadata

# Or: from parlot.instrumentation.livekit import set_session_metadata
set_session_metadata(order_id="12345", crm_ticket="TKT-9")
```

Notes:

- Call after the session has started. Values set with no active session are ignored.
- Keys are normalized to `session.metadata.<name>` (do not invent a different prefix).
- Values are stored as strings. Prefer short identifiers and labels; avoid transcripts or PII that should stay out of session attributes.
- Turn-level custom metadata is not supported yet.

For a single key:

```python
from parlot.core import set_session_attribute

set_session_attribute("retry_count", 2)
```

### External references (searchable IDs)

`add_platform_ref` attaches a searchable external ID to the session (for example a CRM ticket or your own call ID). Paste that value into Parlot session search / resolve to open the matching session.

```python
from parlot.core import add_platform_ref

# Or: from parlot.instrumentation.livekit import add_platform_ref
add_platform_ref("crm_ticket", "TKT-9")
```

Framework adapters stamp their own room / job IDs as `platform.ref.*` during session bootstrap. Use `add_platform_ref` for your own identifiers. Optional `framework=` defaults to `"custom"`:

```python
add_platform_ref("order_id", "ORD-100", framework="shopify")
```

## Errors in the session waterfall

Failed LLM and tool work is surfaced in `spans_agent.error_flag` at ingest. Turn-level `has_error` in session detail is derived at query time: any child operational span under that turn’s `trace_id` with `error_flag = true`.

You do not need a separate turn attribute — fix provider credentials or tool logic locally; Parlot shows the failed span in the waterfall once OTLP reaches the collector. Framework guides document which vendor signals map into `error_flag`.
