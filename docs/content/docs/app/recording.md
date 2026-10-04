---
title: Recording
description: Capture session audio with LiveKit Room Composite egress.
---

# Recording

**Settings → Recording** chooses which agents record session audio. Recording uses LiveKit **Room Composite egress** and is on by default for new agents.

## Why enable recording

Recorded audio powers:

- Playback on the [Timeline](/app/timeline) tab
- Evidence review next to goal and quality scores
- Alignment between what was said and what the agent did

Without a recording, you still get turns, spans, and logs (when captured), but not synced call audio.

## Configuring agents

On the Recording settings page:

- Review the organization default
- Toggle individual agents when you need exceptions
- Run an instrumented agent once if the agent list is empty—Parlot discovers deployments from traffic

## Privacy

Recordings follow your [PII redaction](/app/privacy-redaction) policy. Retention of recording objects is also limited by your [plan](/app/licensing-and-plans).

## Related

- [Timeline](/app/timeline) — listen and scrub
- [Organization settings](/app/organization-settings) — broader workspace controls
