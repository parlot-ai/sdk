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

**Settings → Recording** uses the shared **New agents** allowlist and **Known agents** overrides (Allowlist, Forced on, Forced off). Recording defaults to on for new agents. See [Agent policy allowlists](/app/agent-policy-allowlists) for how those controls work, common setups, and how LiveKit `parlotize(record=…)` can override Settings.

If the Known agents list is empty, run an instrumented agent once so Parlot discovers the deployment.

## Privacy

Recordings follow your [PII redaction](/app/privacy-redaction) policy. Retention of recording objects is also limited by your [plan](/app/licensing-and-plans).

## Related

- [Agent policy allowlists](/app/agent-policy-allowlists) — New agents vs Known agents
- [Timeline](/app/timeline) — listen and scrub
- [Organization settings](/app/organization-settings) — broader workspace controls
