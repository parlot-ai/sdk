---
title: Agent policy allowlists
description: How New agents allowlists and Known agents overrides work for recording, logs, PII redaction, and Gen AI content capture.
---

# Agent policy allowlists

Several **Settings → Agents** pages share the same controls: an allowlist for **new** agents, plus per-agent overrides for **known** agents. That pattern applies to:

- [Recording](/app/recording)
- [Logs and Gen AI content capture](/app/session-logs)
- [PII redaction](/app/privacy-redaction)

Each page has its own policy (what is captured or scrubbed). The allowlist UI works the same way on all of them.

## New agents

The **Allowlist** field is a comma-separated list of agent IDs. Wildcards are allowed—for example `*` (every new agent) or `prod-*`.

When an agent first appears in Parlot, its ID is matched against this list:

- **Match** — the policy is **on** for that agent (recording, log capture, redaction, or content capture, depending on the page).
- **No match** — the policy stays **off** until you change it.

The default allowlist is `*`, so new agents get the policy on. Clear the allowlist to leave the policy off for new agents that only inherit from it.

Agents already listed under **Known agents** keep whatever mode you set there (Allowlist, Forced on, or Forced off). Changing the allowlist does not wipe forced overrides.

## Known agents

Agents show up here after their first session is ingested. For each row you can choose:

| Mode | Meaning |
|------|---------|
| **Allowlist** | Follow the New agents globs. If the ID matches, the policy is on; otherwise it is off. |
| **Forced on** | Always on for this agent, regardless of the allowlist. |
| **Forced off** | Always off for this agent, regardless of the allowlist. |

On **Settings → Logs**, you can also set a minimum log level when capture is forced on.

If the Known agents table is empty, run an instrumented agent once so Parlot discovers the deployment—or rely on the New agents allowlist so the first session already uses the right default.

## Common scenarios

**Keep the defaults.** Leave the allowlist as `*` and leave known agents on Allowlist. Every new deployment gets the policy on.

**Turn the policy off for most new agents.** Clear the New agents allowlist (or remove `*`). New agents that only inherit from Allowlist stay off. Force **on** any known agents that still need the policy.

**Enable only some agent IDs.** Set the allowlist to specific IDs or prefixes (for example `voice-prod, support-*`). New agents outside those patterns stay off. Force **on** or **off** for exceptions in Known agents.

**Exception for one deployment.** Leave the org allowlist as `*`, then set that known agent to **Forced off** (or **Forced on** if the allowlist would otherwise exclude it).

**Same agent, different policies.** Recording, logs, Gen AI content capture, and PII redaction each have their own allowlist and overrides. Turning recording off for an agent does not change its redaction or log settings.

## SDK overrides (`parlotize`)

Dashboard allowlists are not the final word for every policy. The SDK can override Settings for the running process (and LiveKit job metadata can override both):

| Policy | Settings page | SDK override | Notes |
|--------|---------------|--------------|-------|
| Recording | Settings → Recording | LiveKit `parlotize(record=…)` | Bool or agent-id globs. Job metadata `record` wins when present. |
| Session logs | Settings → Logs | `parlotize(capture_logs=…, log_level=…)` | Bool or agent-id globs. |
| Gen AI content | Settings → Gen AI content capture | `parlotize(capture_genai_content=…)` | Process-wide on/off. |
| PII redaction | Settings → PII redaction | *(none)* | Applied in Parlot after ingest from Settings only. |

Precedence for the three capture policies: **job metadata → `parlotize(…)` → Settings allowlist / Known agents → SDK default (on)**. See [Configuration precedence](/sdk/env-vars#configuration-precedence) and [Recording vs telemetry](/sdk/get-started/concepts#recording-vs-telemetry).

If Settings says Forced off but `parlotize(record=True)` (or matching job metadata) is set, recording still runs for that process. Prefer Settings for org-wide defaults; use `parlotize` for environment-specific exceptions (for example disable recording in local dev).

## Related

- [Organization settings](/app/organization-settings) — where these pages live in Settings
- [Agents](/app/agents) — per-agent Settings tab for the same overrides on a single deployment
- [SDK Concepts](/sdk/get-started/concepts#recording-vs-telemetry) — recording, logs, and Gen AI capture in the agent
