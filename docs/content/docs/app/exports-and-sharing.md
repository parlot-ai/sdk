---
title: Exports and sharing
description: Download session artifacts and share read-only session links.
---

# Exports and sharing

Share a read-only session link, or download structured data for offline review.

## Exports (`/exports`)

The **Exports** page lists session export jobs for your organization. From a closed session you
can also start an export from the session header.

Each export is **one closed session** as a downloadable ZIP. Typical contents (toggles in the
dialog):

- Transcript
- Recording (when available)
- Traces
- Logs
- Session metadata (includes goals and evaluation results when present)

Artifacts expire after **72 hours**. Re-run an export if the link has expired. Plan quotas may
limit how many exports Free workspaces can create—see
[Licensing and plans](/app/licensing-and-plans).

## Share links

From a closed session, use **Share** to create a time-bounded link. Recipients open
`/share/:token` with a read-only view—no full workspace login required.

Scopes:

| Scope | What recipients see |
|-------|---------------------|
| **Overview + graph** (default) | Overview and [Topology](/app/topology) |
| **Detailed** | Overview, Topology, Timeline, Quality, Latency, Cost, and Logs |

Revoke or let links expire when a review is finished. Prefer share links when reviewers need
synced audio and span context.

## Related

- [Sessions](/app/sessions) — find the session to share or export
- [Organization settings](/app/organization-settings) — members and client viewer seats for
  ongoing access
