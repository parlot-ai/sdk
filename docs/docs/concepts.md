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

Import from instrumentation packages in agent code — not from `parlot-core` directly.

## Shared span vocabulary

All adapters export the same three layers:

1. **Conversation Contract** — `parlot.session`, `parlot.turn`, `parlot.session.close`, `parlot.agent.handoff`
2. **OTel GenAI** (semconv v1.41.0) — `invoke_agent`, `chat`, `execute_tool {name}`, `invoke_workflow`
3. **Voice** (LiveKit) — `tts`, `stt`, `eou_detection`, `amd`

See [LangGraph](./guides/langgraph.md) and [LiveKit integration](./guides/livekit-integration.md).

## Session and agent identity

- A **session** is one bounded interaction (a call / job).
- `configure(agent_id=..., version=...)` stamps deployment identity used by the Parlot Agents portfolio.
- Version resolution order: `configure(version=)` → `__main__.__version__` → `PARLOT_AGENT_VERSION` → local git SHA (dev only).

Under LiveKit `dev` / job workers, prefer explicit `configure(version=...)` or `PARLOT_AGENT_VERSION`.

## Recording vs telemetry

- **Telemetry** (turns, handoffs, close, usage) always goes over OTLP to `PARLOT_ENDPOINT`.
- **Audio recording** uses LiveKit Room Composite Egress to R2; webhooks confirm upload. Telemetry does not depend on webhooks.

See the [LiveKit guide](./guides/livekit-integration.md) for the full checklist.

## Roadmap adapters

Future packages will use the same GenAI + contract vocabulary (not implemented yet):

- **Google ADK** — lifecycle `before/after_agent|model|tool_callback` → GenAI spans
- **Vercel AI SDK** — `experimental_telemetry` normalize (TypeScript) → GenAI spans
