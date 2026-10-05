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

On **Parlot Cloud**, Settings → Plan & billing shows your Parlot subscription—plan, conversational turn usage, and billing managed through Stripe.

Billing self-serve is a hosted Cloud capability. If you are not on Cloud, the page explains that in-app checkout is unavailable—contact [parlot.ai](https://parlot.ai) for commercial options.

## Agents (policy settings)

Recording, logs, Gen AI content capture, and PII redaction share an [allowlist and per-agent override model](/app/agent-policy-allowlists). Each policy also has its own page:

- [Recording](/app/recording)
- [Session logs and Gen AI content capture](/app/session-logs)
- [PII redaction](/app/privacy-redaction)
- [Conversation boundaries](/app/conversation-boundaries) — idle timeouts and duration caps (separate from allowlists)

## Connections

### API keys

**Settings → API Keys** issues organization ingest credentials for agents (commonly used as `PARLOT_API_KEY` with the SDK). Rotate and revoke keys from the same page when a credential is exposed or unused.

### LLM connections

**Settings → LLM Connections** stores bring-your-own-key (BYOK) credentials for custom [evaluations](/app/evaluations). Judges need a configured connection before custom runs succeed.
