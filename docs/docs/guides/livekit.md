---
title: LiveKit
description: Instrument LiveKit Agents with Parlot — checklist, recording, contract maps, escalation, and OTEL coverage.
sidebar_position: 1
sidebar_custom_props:
  eyebrow: LiveKit
---

# LiveKit

Parlot stays **OpenTelemetry–first**: agent telemetry uses **OTLP** and standard / Parlot semantic attributes. Session **audio** is stored in **Cloudflare R2** via **LiveKit Room Composite Egress**; Parlot confirms uploads with **lazy R2 HEAD reconcile** when you open the session.

> Session transcript, turns, waterfall, usage, and close outcome come from **OTLP** (agent `configure()`). Audio confirmation (`audio_available`) happens when you open `GET /v1/sessions/:id` and the object already exists in R2.

## Get instrumentation working

Two steps are required for full Parlot behavior.

### 1. `configure()` at import (required)

Call before constructing `AgentSession` — patches `AgentSession.__init__`, sets up OTLP export to `PARLOT_ENDPOINT`, and installs turn/handoff/close event hooks.

```python
from parlot.instrumentation.livekit import configure

configure()

from livekit.agents import AgentSession, JobContext, WorkerOptions, cli


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(...)
    await session.start(agent=..., room=ctx.room)
```

`configure()` builds a `TracerProvider` with an OTLP exporter, registers it with `livekit.agents.telemetry`, fetches **`GET /v1/telemetry/bootstrap`** (when `PARLOT_API_KEY` is set), patches `JobContext.connect` to refresh room metadata and **start egress** when recording is enabled, and auto-installs **AgentSession event hooks** (semantic/commit layer) plus span processing (pipeline/waterfall layer).

Session bootstrap runs on LiveKit **`agent_state_changed`** when the agent transitions **`initializing → listening`** (the Starting phase of [AgentSession lifecycle](https://docs.livekit.io/agents/logic/sessions/)). That mints one Parlot **`session.id`**, starts a **`parlot.session`** span for ingestion, and stamps **`platform.ref.*`** keys. Room metadata refresh and egress run after bootstrap (or immediately on `JobContext.connect` if bootstrap already completed). The session closes via the AgentSession **`close`** event.

Optional: `agent_id=` for canonical deployment identity and `version=` for deployment version. Shared kwargs are on [`configure()`](../api/configure.md); LiveKit-only options (`record`, `auto_escalate_sip`, …) are on the [LiveKit API](../api/livekit.md). See also [Concepts](../get-started/concepts.md#session-and-agent-identity).

**Reliable patterns for LiveKit job processes:**

```python
configure(agent_id="restaurant-agent", version="0.1.0")
```

or set `PARLOT_AGENT_VERSION=0.1.0` at deploy/runtime. Under LiveKit `dev` / job workers, prefer those explicit forms — `__main__` is often LiveKit’s IPC entrypoint, not your agent file.

### Canonical agent identity (LiveKit sources)

| Attribute | LiveKit source |
|-----------|----------------|
| `session.agent_id` | `WorkerOptions.agent_name` / job `agent_name`, overridable via `configure(agent_id="…")` |
| `session.agent_framework` | `"livekit"` |
| `session.agent_framework_raw_id` | LiveKit job id (`lk.job_id`) |
| `session.agent_chain` | Deployment id plus runtime routing (`hotel-receptionist → Orchestrator → cancel_task`) |
| `gen_ai.agent.version` | Agent deployment version — see [Concepts](../get-started/concepts.md#session-and-agent-identity) |

LiveKit voice currently uses `conversation_id === session_id` (1:1) as a placeholder until multi-session conversations are modeled.

### Named worker dispatch (`agent_name`)

This is LiveKit’s **dispatch name** (which jobs are eligible for which rooms). It is separate from Parlot `configure(agent_id=…)` / `session.agent_id`, which is the canonical product identity stamped on telemetry.

Prefer an explicit name on the RTC session entrypoint:

```python
from livekit.agents import AgentServer, JobContext

server = AgentServer()


@server.rtc_session(agent_name="healthcare")
async def entrypoint(ctx: JobContext):
    await ctx.connect()
    ...
```

**Why (LiveKit):** without a name, the worker registers as the default (unnamed) agent and is eligible for **automatic assignment** into any room that requests an agent. Paths such as LiveKit `WarmTransferTask` create a second room (often `{room}-human-agent` for briefing). An unnamed worker will be auto-dispatched into that room and run your entrypoint again.

**Why (Parlot):** each LiveKit job bootstraps roughly one `parlot.session`. A second auto-dispatched job therefore creates a **second Parlot session** for the same caller journey (main room + transfer briefing), with its own turns and recording lifecycle. That is usually unwanted in the UI and can surface noisy teardown errors (`engine is closed`, `failed to send session event`) when the briefing room shuts down.

Keep playground, SIP dispatch rules, join tokens, and `lk dispatch` aligned with the same name (`lk dispatch create --agent-name healthcare …`, SIP `room_config.agents` with `agent_name: healthcare`). Local `lk agent console` / `lk agent dev` still work; Cloud and SIP must request the named agent explicitly. See the [healthcare example README](https://github.com/parlot-ai/sdk/blob/main/examples/livekit/healthcare/README.md) for a full WarmTransferTask setup.

### 2. `await ctx.connect()` before `session.start()` (required)

```python
async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(...)
    await session.start(agent=..., room=ctx.room)
```

Without `ctx.connect()` you may still see basic telemetry if you pass `room=ctx.room`, but you will **not** get room audio recording or a reliable `room_sid` for UI linking.

### Environment variables (agent)

| Variable | Role |
|----------|------|
| `PARLOT_ENDPOINT` | Parlot ingest base URL (OTLP, bootstrap, upload-grant). Exporter uses `/v1/traces`. **Required** unless you pass `endpoint=` into `configure()`. |
| `PARLOT_API_KEY` | **Required for recording / bootstrap.** Org-scoped Bearer token minted in Parlot **Settings → API Keys**. |
| `PARLOT_DIAGNOSTICS` | Optional. Default on. Set `off` / `0` / `false` / `no` to disable SDK self-diagnostics (export/handler failures). Metadata only; drops under sustained failure (no retry storm). |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Standard LiveKit Agents credentials (also used to **start** egress). |

Full env reference: [Environment Variables](../api/env-vars.md). Shared `configure()` options: [`configure()`](../api/configure.md).

### Recording policy (LiveKit)

Precedence: job metadata → `configure(record=…)` → Settings → Recording via bootstrap:

- **UI:** Parlot → **Settings → Recording** — per-agent toggles for known deployments, plus globs (`*` or `receptionist*,cal-*`) for agents not yet ingested
- **Code:** `configure(record=True)`, `configure(record=False)`, or `configure(record=["my-agent*"])`
- **Dispatch:** job metadata `{ "record": true }` or `{ "record": false }`

Generative AI content capture (message bodies and tool payloads; default on) is shared across adapters — see [Concepts → Generative AI content capture](../get-started/concepts.md#generative-ai-content-capture). LiveKit job metadata: `{ "capture_genai_content": true|false }`.

### Session application logs

Python `logging` from instrumented agents is captured **on by default** while a Parlot session is active (not `print()` / stdout). Rows appear on the session **Logs** tab.

Precedence (same ladder as recording, but the fallback is **on**):

job metadata `capture_logs` → `configure(capture_logs=…)` → Settings → Logs (bootstrap) → on

- **UI:** Parlot → **Settings → Logs** — globs (default `*`), min level (default `INFO`), per-agent toggles. Empty globs turns capture off org-wide.
- **Code:** `configure(capture_logs=True|False)` or `configure(capture_logs=["my-agent*"], log_level="WARNING")`
- **Dispatch (LiveKit):** job metadata `{ "capture_logs": true|false }`
- Messages are stored as emitted (treat like stdout for PII). Missing bootstrap / old collectors still capture.

### Errors in the session waterfall

Failed LLM and tool work is surfaced in **`spans_agent.error_flag`** at ingest. LiveKit stamps OpenTelemetry **`exception.type`** / **`exception.message`** on spans such as **`llm_request_run`** when a provider call fails; tool failures use **`lk.function_tool.is_error`**. The collector maps those signals (and OTLP span status `ERROR`) into `error_flag` and `error_type` on each operational span row.

Turn-level **`has_error`** is derived at query time — see [Concepts](../get-started/concepts.md#errors-in-the-session-waterfall).

---

## Enable session recording

Recording uses **Room Composite Egress** (OGG, audio-only) to R2. Flow:

1. Agent calls **`POST /v1/recordings/upload-grant`** → JWT-minted temporary R2 credentials (scoped to `{org}/sessions/{sessionId}/`) + canonical `r2://…/audio.ogg` URI.
2. Agent starts egress (OGG → R2) using agent `LIVEKIT_*` credentials.
3. OTLP exports `session.recording.audio_uri`, `session.recording.anchor_wall_ms`, `session.recording.egress_id` with **`audio_available=false`** until confirmation. On egress failure, `session.recording.webhook_error` is stamped instead.
4. Opening `GET /v1/sessions/:id` runs **R2 HEAD reconcile** → `audio_available=true` when the object exists.

### Setup checklist

1. LiveKit Cloud → **Settings → Keys** → create an API key with **`roomRecord`** (needed on the **agent** to start egress via `LIVEKIT_*`).
2. Parlot → **Settings → API Keys** — mint a key for the same org; set it as `PARLOT_API_KEY` on the agent.
3. Enable recording in Parlot → **Settings → Recording** (toggle the agent, or set globs / `*` for new agents), or call `configure(record=True)` / place `{ "record": true }` in job metadata for unnamed dispatches.

### If recording stays “processing”

| Symptom | Likely cause |
|---------|----------------|
| No egress started | Settings → Recording / `configure(record=…)` / job `{ "record": true }`; agent `LIVEKIT_*`; R2 on collector (`503 r2_not_configured`) |
| `audio_available=false` until opened | Expected — open the session to trigger R2 HEAD reconcile |
| No URI in session | Egress failed — check agent logs; grant expired; Settings → Recording / `configure(record=…)` / metadata |
| Delayed confirmation | Parlot **R2 HEAD reconcile** on `GET /v1/sessions/:id` flips `audio_available` after the object lands in R2 |

---

## What gets exported

The conversation attribute contract is framework-agnostic (see [Concepts](../get-started/concepts.md#shared-span-vocabulary)). The LiveKit adapter (`parlot-instrumentation-livekit`) reads LiveKit Agents OTel spans in-process, stamps **Parlot** attributes from `parlot.core.attrs`, emits handoff spans as `parlot.agent.handoff`, and strips all `lk.*` keys before OTLP export (`SanitizeVendorAttrsSpanExporter`).

### Native LiveKit → exported GenAI / voice names

LiveKit still creates vendor span names internally (`llm_request`, `function_tool`, …). Before OTLP export, Parlot remaps them to the shared vocabulary (OTel GenAI semconv v1.41 + voice). Pre-launch: **no native-name export path**.

| LiveKit native (internal) | Exported span name | `gen_ai.operation.name` | `agent.role` | Notes |
|---|---|---|---|---|
| `llm_node` / `llm_request` / `llm_request_run` | `chat` / `chat {model}` | `chat` | `llm` | Stage keeps `node` / `request` / `run` |
| `function_tool` | `execute_tool {name}` | `execute_tool` | `tool` | Tool payloads on Parlot attrs |
| `tts_node` / `tts_request_run` | `tts` | — | `tts` | Voice layer |
| `eou_detection` | `eou_detection` | `end_of_utterance_detection` | `stt` | |
| `amd` | `amd` | `classify_contact` | `amd` | |
| `drain_agent_activity` | `invoke_agent` | `invoke_agent` | `pipeline` | |
| `user_turn` / `agent_turn` | **not exported** | — | — | Contract `parlot.turn` is source of truth; pipeline attrs (latency, STT confidence, media alignment) are stamped onto `parlot.turn` before drop |
| `parlot.agent.handoff` | `parlot.agent.handoff` | `agent_handoff` | `handoff` | |

When a span carries explicit `agent.role`, the collector prefers that value.

### Span name → `agent.stage` (timeline labels)

Each operational span carries `agent.stage` (from the native LiveKit name before rename). UI labels combine role + stage — e.g. `llm` + `run` → **LLM · API call**. Nested LiveKit LLM spans all export as `chat` with distinct stages.

| Native LiveKit span | `agent.stage` | UI label |
|---|---|---|
| `llm_node` | `node` | LLM · inference |
| `llm_request` | `request` | LLM · request |
| `llm_request_run` | `run` | LLM · API call |
| `tts_node` | `node` | TTS · synthesis |
| `tts_request_run` | `run` | TTS · API call |

In **events mode**, trust committed conversation items for authoritative agent utterance text on `parlot.turn`.

### Vendor attribute → Parlot attribute (export)

| LiveKit attribute (read in processor) | Parlot attribute (OTLP) |
|---|---|
| `lk.instructions` / `lk.chat_ctx` | `agent.instructions_excerpt`; on `llm_node`, last `role=user` message from chat context → `turn.user_text` (excludes `function_call` items) |
| `lk.function_tools` | `agent.tool.names` (JSON array) |
| `lk.function_tool.name` | `agent.tool.name` |
| `lk.function_tool.is_error` | `agent.tool.is_error` |
| `lk.user_transcript` / `lk.user_input` | `turn.user_text` |
| `lk.response.text` | `turn.agent_text` |
| `lk.e2e_latency` | `turn.e2e_latency_s` |
| `lk.response.ttft` | `turn.llm_ttft_s` |
| `lk.transcript_confidence` | `voice.stt.confidence` |
| `lk.transcription_delay` | `turn.transcription_delay_s` |
| `lk.end_of_turn_delay` | `turn.eou_delay_s` |
| `lk.participant_identity` | `participant.channel_identity`, `session.user_id` |
| `lk.eou.language` | `voice.eou.language` |
| `lk.amd.category` | `voice.amd.category` |

### Turn metrics (LiveKit source → Parlot histogram)

Pipeline timing is read from native `agent_turn` / `tts_*` spans and stamped onto **`parlot.turn`** (and metrics) before those native turn spans are dropped from export.

| Parlot metric | Source (native, pre-export) | LiveKit attribute |
|---|---|---|
| `turn.e2e_latency_ms` | `agent_turn` → `parlot.turn` | `lk.e2e_latency` |
| `turn.llm_ttft_ms` | `agent_turn` → `parlot.turn` | `lk.response.ttft` |
| `turn.tts_ttfb_ms` | `tts` (from `tts_node`) | `lk.response.ttfb` |
| `turn.transcription_delay_ms` | `agent_turn` → `parlot.turn` | `lk.transcription_delay` |
| `turn.eou_delay_ms` | `agent_turn` → `parlot.turn` | `lk.end_of_turn_delay` |

LiveKit-native `lk.agents.turn.*` and `lk.agents.usage.*` metrics may still land in `otel_metrics_raw` but are **not** used by the Parlot pipeline.

### Session close (`parlot.session.close`)

| LiveKit `CloseReason` | `session.close_reason` |
|---|---|
| `participant_disconnected` | `participant_disconnected` |
| `user_initiated` | `user_initiated` |
| `error` | `error` |
| `task_completed` | `task_completed` |
| `job_shutdown` | `job_shutdown` |

Primary emission: `AgentSession.on("close")` via event hooks.

### AgentSession events (semantic / commit layer)

When `configure()` patches `AgentSession`, Parlot subscribes to LiveKit events for **turn boundaries and session aggregates**. Operational waterfall detail stays on OTel spans.

| LiveKit event | Parlot output |
|---|---|
| `agent_state_changed` (`initializing` → `listening`) | Session bootstrap: `parlot.session`, ContextVar scope, deferred room refresh + egress |
| `conversation_item_added` (user/assistant message) | `parlot.turn` root trace per committed message; deduped by item id |
| `conversation_item_added` (`agent_handoff`) | `parlot.agent.handoff` span + session handoff count / agent chain |
| `user_input_transcribed` (final) | Pending `speaker_id` / language for next user turn (`livekit_stt_event` diarization). Set STT `language: "multi"` (or equivalent auto-detect mode) so `UserInputTranscribedEvent.language` is populated and stamped on `turn.language`. |
| `function_tools_executed` | `session.tool_call_count` (batch count; individual tool spans still export) |
| `session_usage_updated` | Authoritative `session.total_*_tokens` (overrides span accumulation) |
| `error` (non-recoverable) | `session.close_error` on close when no explicit close error |
| `close` | `parlot.session.close` with normalized `session.close_reason` |

Span-based turn emission (`user_turn` / `agent_turn` → `parlot.turn`) is **disabled** once event hooks install (`turn_source=events`). Native turn spans are still observed to copy latency / STT confidence / media alignment onto `parlot.turn`, then dropped from export. Semantic session lifecycle (bootstrap, turns, close, tokens) does **not** depend on the `job_entrypoint` span.

### Export allowlist (LiveKit)

Spans exported to Parlot (after rename): Conversation Contract (`parlot.session`, `parlot.turn`, `parlot.session.close`, `parlot.agent.handoff`), GenAI (`chat` / `chat {model}`, `execute_tool {name}`, `invoke_agent`), and voice (`tts`, `stt`, `eou_detection`, `amd`).

---

## Human escalation

Semantics and role vocabulary (`user` / `agent` / `human_rep`) are in [Concepts → Human escalation](../get-started/concepts.md#human-escalation). Below are LiveKit-specific ways to signal a live rep.

### Explicit call

```python
from parlot.instrumentation.livekit import record_human_rep

record_human_rep("support_rep_jane", label="Jane")
```

### SIP warm transfer (auto-detect)

If you use `WarmTransferTask` (or any flow that opens a second agent room), set a named LiveKit [`agent_name`](#named-worker-dispatch-agent_name) on `@server.rtc_session` so the briefing room does not auto-dispatch another copy of your worker and mint a duplicate Parlot session.

```python
from parlot.instrumentation.livekit import configure

configure(auto_escalate_sip=True)
```

Or match participant metadata:

```python
configure(
    escalation_metadata_match={
        "type": "agent_transfer",
        "is_human": "true",
    }
)
```

### Context manager around a dial

```python
from parlot.instrumentation.livekit import human_escalation

async def transfer_to_support_desk(session, sip_uri):
    with human_escalation(label="L2 Support Queue"):
        await session.dial(sip_uri)
```

---

## Custom metadata and refs

Semantics are in [Concepts → Custom metadata and external references](../get-started/concepts.md#custom-metadata-and-external-references). Import the same helpers from the LiveKit package:

```python
from parlot.instrumentation.livekit import (
    set_session_metadata,
    set_session_attribute,
    add_platform_ref,
)

set_session_metadata(order_id="12345", crm_ticket="TKT-9")
set_session_attribute("retry_count", 2)
add_platform_ref("crm_ticket", "TKT-9")
# optional framework= for your own IDs:
add_platform_ref("order_id", "ORD-100", framework="shopify")
```

Call after the session has started (`agent_state_changed` → listening). LiveKit room / job IDs are stamped automatically as `platform.ref.*` during session bootstrap.

---

## LiveKit observability (OTEL): enabled vs disabled

This section describes what Parlot stores and surfaces when LiveKit Agents **pipeline tracing** is active vs when it is not. It is **not** about whether the agent calls `parlot.configure()` — Parlot instrumentation must stay on for any ingest.

### Terminology

| Setting | Meaning |
|---------|---------|
| **`parlot.configure()` on** | Required. Parlot registers a `TracerProvider` with `livekit.agents.telemetry`, exports OTLP to Parlot, and installs AgentSession event hooks. |
| **LiveKit pipeline OTEL on** | LiveKit emits internal spans (`user_turn`, `agent_turn`, `llm_node`, `tts_node`, `function_tool`, `eou_detection`, `amd`, …) into the active tracer. With Parlot configured, those spans are enriched and exported. |
| **LiveKit pipeline OTEL off** | LiveKit does not emit pipeline spans (or tracing is a noop). Parlot still exports **event-sourced** spans (`parlot.session`, `parlot.turn`, `parlot.agent.handoff`, `parlot.session.close`) and any spans Parlot creates itself. |

Session **bootstrap and close no longer depend on `job_entrypoint`**. Bootstrap runs on `agent_state_changed` when the agent transitions **`initializing → listening`** ([AgentSession lifecycle](https://docs.livekit.io/agents/logic/sessions/)); close runs on the AgentSession **`close`** event ([events reference](https://docs.livekit.io/reference/agents/events/)).

### Empirical comparison (same agent, two local sessions)

These sessions exercised the hotel-receptionist agent against the same local stack; only LiveKit pipeline OTEL differed:

| | OTEL **on** `019e801e…` | OTEL **off** `019e8020…` |
|---|---|---|
| Duration | ~54s, 9 turns | ~73s, 10 turns |
| **`sessions` row** | Yes — voice, livekit, closed (`tool_failure`) | Yes — same shape |
| **`session_turns`** | 9 rows (user + agent roles) | 10 rows |
| **`session_agents` waterfall** | 48 spans (`llm`, `tts`, `tool`, `stt`, `pipeline`, `handoff`) | 83 spans (same roles; longer call → more rows) |
| **Transcript / redacted previews** | 14 `span_content_redacted` rows | 23 rows |
| **Handoffs** | 4 (`session_handoffs`) | 4 |
| **Session aggregates** | tokens, turn count, tool count, agent chain, topology, intent | Same fields populated |
| **External refs** | room/job/platform refs | Same |
| **Turn sentiment (close worker)** | 4 user turns scored | 5 user turns scored |
| **`turn.e2e_latency_ms` metric** | Present (11 points) | **Absent** |
| **`turn.e2e_latency_s` on spans** | 1 span | **0** |
| **`voice.stt.confidence`** | 1 `stt` span | 2 `stt` spans |
| **`media_segment_*` on turns** | All `0` | All `0` |
| **Recording** | `audio_available=false` (egress quota) | Same |

Both sessions received a **full semantic session record** and a **non-empty waterfall**. The clearest OTEL-on-only signal in this pair was **end-to-end turn latency** (`turn.e2e_latency_s` / `turn.e2e_latency_ms`), which is sourced from `lk.e2e_latency` on LiveKit **`agent_turn`** spans. Neither session populated non-zero `turn.llm_ttft_ms`, `turn.tts_ttfb_ms`, `turn.transcription_delay_ms`, or `turn.eou_delay_ms` (metrics rows existed but summed to zero).

### Coverage matrix

| Capability | OTEL off (events + Parlot) | OTEL on (+ LiveKit pipeline spans) |
|---|---|---|
| Session resolve, id, channel, framework, duration | Yes | Yes |
| Platform external refs (`room_sid`, `job_id`, …) | Yes | Yes |
| Turn timeline (who said what, turn index, trace-per-turn) | Yes — `conversation_item_added` → `parlot.turn` | Yes |
| Session close reason / close error | Yes — `close` / `error` events | Yes |
| Token totals | Yes — `session_usage_updated` | Yes (+ per-span usage on LLM rows when spans fire) |
| Tool call **count** | Yes — `function_tools_executed` | Yes |
| Handoffs (count, chain, `session_handoffs`) | Yes — `agent_handoff` items + spans | Yes |
| Intent / topology / agent chain at close | Yes — derived server-side | Yes — richer when LLM spans carry `agent.instructions_excerpt` |
| **Per-turn latency histograms** | Partial — from `ChatMessage.metrics` on committed items when LiveKit attaches them ([per-turn latency](https://docs.livekit.io/deploy/observability/data.md#per-turn-latency)) | **Full** — `agent_turn` / `tts_node` / `user_turn` `lk.*` attrs → `turn.*` metrics |
| **Waterfall: LLM / TTS / tool rows** | Only if pipeline spans still emit* | Yes — `llm_node`, `tts_node`, `function_tool`, … |
| **STT confidence** (`voice.stt.confidence`) | Unreliable — needs `user_turn` span | Yes — on `stt` role rows |
| **EOU / AMD** (`eou_detection`, `amd` spans) | No | Yes — when enabled in the agent |
| **Provider errors on spans** (`error_flag`, `exception.*`) | No failed-provider rows | Yes — failed `llm_request_run` / `function_tool` |
| **Per-tool I/O previews** | Batch count only from events | Yes — `tool.input/output.payload_preview` on tool spans |
| **Audio ↔ turn alignment** (`media_segment_*`, `speech_wall_*`) | **No** today (events path does not stamp timing) | Yes — from `user_turn` / `agent_turn` span timestamps |
| **Turn `has_error` in UI** | Stays false (derived from child `session_agents.error_flag`) | Yes when a child span errors |
| **Fleet interaction graph / per-agent latency edges** | Degraded — few operational edges | Yes — needs LLM/tool span graph |
| Session recording (R2 egress) | Yes — independent of pipeline OTEL | Yes |

\*When `parlot.configure()` registers the tracer provider, LiveKit may still emit pipeline spans even if LiveKit Cloud observability is toggled off elsewhere. Treat “OTEL off” as **no pipeline spans reaching Parlot**, not merely disabling a cloud dashboard.

### What Parlot can promise without LiveKit pipeline OTEL

With **`parlot.configure()` only** (events + Parlot OTLP, no LiveKit pipeline spans):

- **Episode record** — paste session id → read the call: turns, roles, text, close outcome, coarse usage, handoffs, intent label.
- **Session list / search** — metadata, end state, token totals, participant count.
- **Evals on transcript** — session-close workers can still score user turns from stored text.
- **Recording** — egress to R2 when `PARLOT_API_KEY` and recording policy are set; audio confirms via R2 reconcile when the session is opened.

**Not available** (or materially degraded) without pipeline spans:

- Expanded **turn waterfall** (LLM/TTS/tool timing tree) and **span detail panel** I/O.
- **Turn-level latency charts** beyond what `ChatMessage.metrics` provides on committed messages.
- **STT quality**, **EOU**, and **AMD** pipeline signals.
- **Accurate `has_error` per turn** and provider-level failure attribution.
- **Audio segment bars** synced to turns (`media_segment_*` stays at 0).
- **Fleet graph** and per-agent operational analytics.

### Recommendation

- **Debugging / SRE / latency work:** keep LiveKit pipeline OTEL active and `parlot.configure()` on. The waterfall, error attribution, and latency histograms depend on it.
- **Transcript-only / compliance / eval workflows:** `parlot.configure()` + AgentSession events are sufficient for the semantic session record; do not expect a populated debugger waterfall.
- **Never disable all tracing** if you still call `parlot.configure()` — Parlot replaces the provider. “Turn off OTEL” should mean disabling LiveKit’s pipeline span emission or not routing it to Parlot, not removing Parlot instrumentation.

---

## Mental model

**Two layers:** LiveKit **events** commit conversational semantics (turns, handoffs, usage, close). LiveKit **OTel spans** carry the pipeline waterfall (LLM, TTS, tools, AMD, EOU). The adapter maps both to Parlot OTLP keys; the collector stays framework-agnostic.

| Source | Configured by | Carries |
|--------|----------------|--------|
| **OTLP** | Agent (`PARLOT_*`, `configure()`) | Traces, refs, optimistic `session.recording.audio_uri`, anchor, `session.recording.egress_id`, or `session.recording.webhook_error` |
| **Upload grant** | Agent → collector | Scoped temp R2 creds (`session_token`) for LiveKit egress |
| **R2 reconcile** | Session API (lazy) | Confirms upload → `audio_available=true` when the object exists |

For platform env (`R2_ACCOUNT_ID`, `R2_CONTENT_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` on collector + API, `DATABASE_URL`), see the platform local E2E runbook. R2 key scheme: `{tenant_id}/sessions/{session_id}/audio.ogg`.
