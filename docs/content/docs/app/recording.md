---
title: Recording
description: Capture session audio from LiveKit, Pipecat, or BYO ingest — playback by session.
---

# Recording

**Settings → Recording** chooses which agents record session audio. Recording is on by default
for new agents. Capture is adapter-specific; Parlot normalizes every source into the same
playback and redaction pipeline.

## Sources

| Source | How audio lands |
|--------|-----------------|
| **LiveKit** | Room Composite egress → Opus/OGG object (stream-copied when already conformant) |
| **Pipecat** | Agent uploads stereo WAV segments (~30s) via upload-grant → stitch + normalize |
| **BYO ingest** | Agent uploads via the same grant → same stitch/normalize/redact path |
| **BYO link-only** | External URI stamped for UI; rejected when tenant PII redaction is on |

Playback always uses a **signed URL for the session’s current playable asset** (redacted when
policy requires).

## Why enable recording

Recorded audio powers:

- Playback on the [Timeline](/app/timeline) tab
- Evidence review next to goal and quality scores
- Alignment between what was said and what the agent did

Turns, spans, and logs still appear when capture is on. Synced call audio needs recording
enabled.

## Configuring agents

**Settings → Recording** uses the shared **New agents** allowlist and **Known agents** overrides
(Allowlist, Forced on, Forced off). Recording defaults to on for new agents. See
[Agent policy allowlists](/app/agent-policy-allowlists) for how those controls work, common
setups, and how `parlotize(record=…)` can override Settings.

If the Known agents list is empty, run an instrumented agent once so Parlot discovers the
deployment.

## Privacy

Recordings follow your [PII redaction](/app/privacy-redaction) policy. Redaction beeps are
**close-gated** (need turn PII indexes × media segment bounds against the stitched file).
Retention of recording objects is also limited by your [plan](/app/licensing-and-plans).

## Related

- [Agent policy allowlists](/app/agent-policy-allowlists) — New agents vs Known agents
- [Timeline](/app/timeline) — listen and scrub
- [Organization settings](/app/organization-settings) — broader workspace controls
- [Pipecat guide](/sdk/guides/pipecat) — `ParlotRecordingProcessor` placement
