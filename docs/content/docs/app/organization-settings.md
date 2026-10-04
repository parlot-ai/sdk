---
title: Organization settings
description: Members, billing, API keys, LLM connections, pricing, and workspace profile.
---

# Organization settings

Open **Settings** from the app shell to manage the workspace. Navigation is grouped into Workspace, Agents, and Connections.

## Workspace

### General

Edit the organization display name and view tenant identity metadata. Cloud deployments may also show organization lifecycle controls (for example danger-zone deletion) when available.

### Members

Invite teammates and assign roles appropriate to your deployment:

- **Internal seats** — day-to-day builders and operators (administrators and members).
- **Client viewers** — read-oriented access for stakeholders (when your plan includes viewer seats).

Free plans include a small internal seat allowance (three seats). Paid plans raise or remove seat ceilings—see [Licensing and plans](/app/licensing-and-plans).

### Plan & billing

On **Parlot Cloud**, Settings → Plan & billing shows your Parlot subscription: plan, conversational turn usage, and Stripe-managed actions (upgrade, portal, and related flows).

Billing self-serve is a hosted Cloud capability. If you are not on Cloud, the page explains that in-app checkout is unavailable—contact [parlot.ai](https://parlot.ai) for commercial options.

## Agents (policy settings)

Documented in depth on their own pages:

- [Recording](/app/recording)
- [Session logs and Gen AI content capture](/app/session-logs)
- [PII redaction](/app/privacy-redaction)
- [Conversation boundaries](/app/conversation-boundaries)

### Cost & margin

Provider rates and margin analytics live under **Observe → [Cost & margin](/app/cost)** (`/cost`), not under Settings. See [Cost](/app/cost) for the rate card, unpriced models, telephony estimates, and margin.

This is separate from **Plan & billing** (your Parlot subscription).

## Connections

### API keys

**Settings → API Keys** issues organization ingest credentials for agents (commonly used as `PARLOT_API_KEY` with the SDK). Rotate and revoke keys from the same page when a credential is exposed or unused.

### LLM connections

**Settings → LLM Connections** stores bring-your-own-key credentials for custom [evaluations](/app/evaluations). Judges need a configured connection before custom runs succeed.
