---
title: Latency
description: Turn and pipeline latency analysis for a session.
---

# Latency

The **Latency** tab (`/sessions/:sessionId/latency`) focuses on how long each stage of the conversation took.

## What it covers

Depending on modality and instrumentation, you may see:

- End-to-end turn latency
- Large language model (LLM) time-to-first-token and generation time
- Speech-to-text (STT) and text-to-speech (TTS) delays
- Tool calls wait time
- Dead air or gaps between turns

Use the latency threshold control (when present) to highlight slow stages for quality review—without needing raw span IDs in the main list.

## Goal and quality context

Latency sits next to outcome analysis in the session shell. When goal completion, sentiment, or topic results are available for the session, use them alongside slow turns to decide whether delay caused abandonment or transfer.

For fleet-level speed trends, start on [Overview](/app/overview) or the agent workspace Latency tab, then drill into individual sessions here.

## Related settings

Accurate voice timing benefits from [recording](/app/recording) anchors. Pipeline content visibility depends on [Gen AI content capture](/app/session-logs).
