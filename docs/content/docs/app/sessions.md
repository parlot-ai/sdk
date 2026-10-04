---
title: Sessions
description: Find sessions, paste vendor IDs, and open the session debugger.
---

# Sessions

The **Sessions** list (`/sessions`) is the searchable index of interactions Parlot has ingested. Open a row to enter the session debugger (Overview, Timeline, Latency, Cost, Flow, Logs).

## Filters

Narrow the list by attributes such as:

- Date range
- Channel (voice, webchat, SMS, WhatsApp, and custom channels when present)
- Agent and version
- Outcome (resolved, transferred, abandoned, error, and related states)
- Topic or subtopic when classification is available

Combine filters to answer questions like “abandoned voice calls for receptionist last week.”

## Lifecycle states

Sessions move through states you may see in the list or detail banner:

- **Live / open** — Interaction still in progress; some analytics finalize after close.
- **Closing** — Post-session pipeline (redaction, evaluations, projections) is running.
- **Closed** — Ready for full timeline, cost, share, and export.
- **Stuck / attention** — Close processing needs attention; use the banner guidance in the UI.

## Paste-to-search and command palette

Operators often have a vendor identifier, not a Parlot session ID. Paste into Sessions search or the command palette (Ctrl/Cmd+K):

| What you paste | Typical source |
|----------------|----------------|
| LiveKit room SID (`RM_…`) | LiveKit Cloud → Rooms |
| LiveKit job ID | Agent worker logs |
| OpenTelemetry trace ID (32 hex characters) | Trace backends or logs |
| Parlot session ID (32 hex characters) | Parlot URLs and exports |

Parlot resolves the paste to the matching session when an external reference was indexed at ingest. If several matches exist (for example a reused room name), the UI asks you to disambiguate.

## Opening a session

From the list, open a session to use:

- [Timeline](/app/timeline) — turns, transcript, audio
- [Latency](/app/latency) — speed analysis
- [Cost](/app/cost) — spend breakdown
- [Flow](/app/flow) — multi-agent handoffs
- [Logs](/app/session-logs) — captured runtime logs

Closed sessions also support [Share and Export](/app/exports-and-sharing).
