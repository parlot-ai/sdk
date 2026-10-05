---
title: Agents
description: Portfolio of agent deployments and the per-agent workspace.
---

# Agents

The **Agents** area shows every instrumented deployment that has sent traffic to Parlot.

## Portfolio (`/agents`)

Each card represents an agent identity from your SDK configuration (typically the `agent_id` and optional version you pass to `parlotize()`). Cards surface recent activity, health, and shortcuts into the workspace.

If the list is empty, complete the [SDK Quick Start](/sdk/get-started/quick-start) and run a real or test session so telemetry can register the deployment.

## Agent workspace (`/agents/:agentId`)

Open an agent for a deeper view. Tabs typically include:

- **Overview** — Volume, outcomes, and high-level trends for this deployment.
- **Latency** — Turn and pipeline latency for this agent.
- **Cost** — Spend attributed to this agent.
- **Topology / flow** — How this deployment hands off among specialized agents (see also the session [Flow](/app/flow) tab).
- **Topics** — Topic catalog for this agent (labels, reuse versus newly created topics).
- **Versions** — Version history when you stamp versions in the parlotize() call.
- **Settings** — Overrides for recording, log capture, and related agent-scoped policies (same [allowlist modes](/app/agent-policy-allowlists) as organization Settings).

## How agents appear

Agents are discovered from telemetry after instrumented traffic arrives. You do not manually register a deployment in the dashboard for basic observability. Keep `agent_id` stable across releases so history stays on one card; bump version when you want to compare releases.

## Related settings

Organization-wide defaults that affect agents live under Settings. Recording, logs, Gen AI content capture, and PII redaction share [Agent policy allowlists](/app/agent-policy-allowlists):

- [Recording](/app/recording)
- [Session logs and capture](/app/session-logs)
- [Personally identifiable information (PII) redaction](/app/privacy-redaction)
- [Conversation boundaries](/app/conversation-boundaries)
