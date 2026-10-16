---
title: Latency
description: Turn and pipeline latency analysis for a session.
---

# Latency

The **Latency** tab (`/sessions/:sessionId/latency`) focuses on how long each stage of the
conversation took.

## What it covers

Depending on channel and how your agent is instrumented, you may see:

- End-to-end turn latency
- Large language model (LLM) time-to-first-token and generation time
- Speech-to-text (STT) and text-to-speech (TTS) delays
- Tool call wait time
- Dead air or gaps between turns

For highlighting slow stages on the turn list, use the latency threshold control on
[Timeline](/app/timeline).

## Goal and quality context

Use [Quality](/app/quality) for outcome, goal, sentiment, and evaluation results. Pair slow turns
here with those signals to decide whether delay contributed to abandonment or escalation.

For fleet-level speed trends, start on [Overview](/app/overview) or the agent workspace Latency
tab, then drill into individual sessions here.

## Related settings

Accurate voice timing benefits from [recording](/app/recording) anchors. Pipeline content
visibility depends on [Gen AI content capture](/app/session-logs).
