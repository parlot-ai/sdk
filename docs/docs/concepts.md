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
| `parlot-core` | Semantic conventions, base processor, UUID v7 session ids |
| `parlot-instrumentation-livekit` | LiveKit Agents OTel instrumentation, egress hooks, platform refs |

Import from instrumentation packages in agent code — not from `parlot-core` directly.

## Session and agent identity

- A **session** is one bounded interaction (a call / job).
- `configure(agent_id=..., version=...)` stamps deployment identity used by the Parlot Agents portfolio.
- Version resolution order: `configure(version=)` → `__main__.__version__` → `PARLOT_AGENT_VERSION` → local git SHA (dev only).

Under LiveKit `dev` / job workers, prefer explicit `configure(version=...)` or `PARLOT_AGENT_VERSION`.

## Recording vs telemetry

- **Telemetry** (turns, handoffs, close, usage) always goes over OTLP to `PARLOT_ENDPOINT`.
- **Audio recording** uses LiveKit Room Composite Egress to R2; webhooks confirm upload. Telemetry does not depend on webhooks.

See the [LiveKit guide](./guides/livekit.md) for the full checklist.
