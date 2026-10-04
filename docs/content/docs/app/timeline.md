---
title: Timeline
description: Turn-by-turn transcript, synced audio, and span waterfall.
---

# Timeline

The **Timeline** tab (`/sessions/:sessionId/timeline`) is the primary debugger for what happened in a session, in order.

## Conversational turns

A **turn** is one complete contribution by a participant (caller, AI agent, or human representative). Timeline lists turns chronologically with transcript text when available.

For voice, turn boundaries usually follow end-of-utterance from the voice pipeline. For text and messaging, each discrete message is typically a turn.

## Audio playback

When [recording](/app/recording) captured session audio:

- Use the audio player to scrub the call
- Select a turn to jump playback to that segment when timing anchors are present
- Collapse the player when you only need the transcript

If no recording is available, Timeline still shows turns and spans; the audio zone explains why playback is missing.

## Span waterfall

Expand a turn (or use the detail panel) to see child work such as:

- Speech-to-text (STT)
- Large language model (LLM) calls
- Tool or application programming interface (API) calls
- Text-to-speech (TTS)

Open a span for attributes and input/output previews (subject to [Gen AI content capture](/app/session-logs) and [PII redaction](/app/privacy-redaction) settings). Shareable span URLs use `/sessions/:sessionId/spans/:spanId`.

## Speakers

Timeline distinguishes participants when diarization or agent identity is available:

- Caller / user
- AI agents (by agent identity)
- Human representatives after escalation

Until post-session speaker separation finishes, some human audio may appear under a generic user lane.

## Tips

- Use Timeline together with [Flow](/app/flow) when failures involve handoffs.
- Use [Latency](/app/latency) when you care about percentiles and thresholds more than narrative order.
- Evidence chips from quality analysis can highlight proving turns on the same timeline.
