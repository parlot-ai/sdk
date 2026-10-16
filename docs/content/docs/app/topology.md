---
title: Topology
description: Multi-agent handoffs and cascading failure debugging.
---

# Topology

The **Topology** tab (`/sessions/:sessionId/topology`) visualizes how work moved between agents
(and humans) during the session.

## Why topology matters

Production voice systems often use more than one agent. A greeter may transfer to a specialist,
tools may call out, and a human representative may join. Topology shows the handoff map so you
can answer “which agent broke it?” from the graph.

## Reading the canvas

- **Nodes** represent participants such as the caller, AI agents, interactive voice response
  (IVR) systems, or human representatives.
- **Edges** represent transfers or handoffs, often with reason and timing context when
  instrumentation emitted it.
- Select a node or edge to inspect details in the side panel.

Agent-level topology also appears in the [Agents](/app/agents) workspace for a deployment’s
lasting handoff patterns across many sessions.

## Cascading failures

When a late agent fails, the root cause may be an earlier handoff with bad context or a slow
tool. Trace edges backward from the failing node, then open the related turns on
[Timeline](/app/timeline) for span-level proof.

## Related reading

- [Timeline](/app/timeline) for chronological evidence
- [Latency](/app/latency) when delays sit on a handoff edge
