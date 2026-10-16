---
title: Sessions
description: Find sessions, paste vendor IDs, and open the session debugger.
---

# Sessions

The **Sessions** list (`/sessions`) is the searchable index of interactions Parlot has ingested.
Open a row to enter the session debugger (Overview, Timeline, Quality, Latency, Cost, Topology,
Logs).

## Filters

Narrow the list by attributes such as:

- Date range
- Channel (voice, webchat, SMS, WhatsApp, and custom channels when present)
- Agent and version
- Outcome (Completed, Escalated, Abandoned, Partial, Error, Stuck)
- Topic or subtopic when classification is available

Combine filters to answer questions like “abandoned voice calls for receptionist last week.”

## Lifecycle states

Sessions move through states you may see in the list or detail banner:

- **Live** — Interaction still in progress; some analytics finalize after close.
- **Closing** — Post-session pipeline (redaction, evaluations, analytics updates) is running.
- **Retrying** — Close processing is retrying a recoverable step.
- **Stuck** — Close processing needs attention; use the banner guidance in the UI.
- **Closed** — Ready for full timeline, cost, share, and export.

## Paste-to-search and command palette

Operators often paste a vendor or business ID into Sessions search or the command palette
(Ctrl/Cmd+K):

| What you paste | Typical source |
|----------------|----------------|
| LiveKit room SID (`RM_…`) | LiveKit Cloud → Rooms |
| LiveKit job ID | Agent worker logs |
| OpenTelemetry trace ID (32 hex characters) | Trace backends or logs |
| Parlot session ID (32 hex characters) | Parlot URLs and exports |
| Your own external IDs | Values you stamped with `add_platform_ref` (see below) |

Parlot resolves the paste to the matching session when an external reference was indexed at
ingest. If several matches exist (for example a reused room name), the UI asks you to
disambiguate.

### Custom searchable IDs

Framework adapters already index LiveKit room/job IDs and similar refs. To make your own
identifiers paste-searchable (CRM ticket, `client_id`, order ID, and so on), stamp them from the
agent with `add_platform_ref`:

```python
from parlot.core import add_platform_ref

add_platform_ref("client_id", "acme-42")
# Or: add_platform_ref("order_id", "ORD-100", framework="shopify")
```

After the session is ingested, pasting `acme-42` (or `ORD-100`) into Sessions search or the
command palette opens that session. See
[Custom metadata and external references](/sdk/get-started/concepts#custom-metadata-and-external-references)
in the SDK Concepts guide.

### Custom metadata (display only)

`set_session_metadata` stores key/value pairs under `session.metadata.*` for display on the
session Overview (and for product features such as cost margin grouping via
`session.metadata.client`). For paste lookup, use `add_platform_ref`.

## Opening a session

From the list, open a session to use:

- [Timeline](/app/timeline) — turns, transcript, audio
- [Quality](/app/quality) — outcomes, goals, sentiment, topics, custom evals
- [Latency](/app/latency) — speed analysis
- [Cost](/app/cost) — spend breakdown
- [Topology](/app/topology) — multi-agent handoffs
- [Logs](/app/session-logs) — captured runtime logs

Closed sessions also support [Share and Export](/app/exports-and-sharing).
