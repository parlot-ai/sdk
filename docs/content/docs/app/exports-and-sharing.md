---
title: Exports and sharing
description: Download session artifacts and share read-only session links.
---

# Exports and sharing

Collaborate without granting full dashboard access, or pull structured data for offline review.

## Exports (`/exports`)

The **Exports** page lists asynchronous export jobs for your organization. From a closed session you can also start an export from the session header.

Typical uses:

- Download transcripts and evaluation results for a session set
- Hand artifacts to compliance or offline analysis tools

Export jobs produce downloadable artifacts that expire after a retention window shown in the UI (commonly on the order of days). Re-run an export if the link has expired. Plan quotas may limit how many exports Free workspaces can create—see [Licensing and plans](/app/licensing-and-plans).

## Share links

From a closed session, use **Share** to create a time-bounded link. Recipients open `/share/:token` without signing in as a full workspace member.

Shared viewers can browse a read-only subset of session tabs (Overview, Timeline, Latency, Cost, Flow, Logs—labels may match the current product shell). They cannot change settings or run exports unless your product later grants those actions on the share surface.

Revoke or let links expire when a review is finished. Prefer share links over screenshots when reviewers need synced audio and span context.

## Related

- [Sessions](/app/sessions) — find the session to share or export
- [Organization settings](/app/organization-settings) — members and client viewer seats for ongoing access
