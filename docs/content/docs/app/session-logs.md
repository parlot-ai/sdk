---
title: Session logs and capture
description: Runtime logs, Gen AI content capture, and how they appear on a session.
---

# Session logs and capture

The **Logs** tab (`/sessions/:sessionId/logs`) shows runtime logs captured from instrumented agents for that session. Capture policy lives under Settings.

## Logs tab

Use Logs to:

- Correlate application log lines with the same session you are debugging on Timeline
- Filter by severity (for example DEBUG, INFO, WARN, ERROR) when the UI exposes levels
- Open a log detail panel for stack traces and structured fields

Logs appear when capture is enabled for the agent and the SDK/agent process emitted logging that Parlot ingested.

## Settings → Logs

**Settings → Logs** controls whether Python logging from instrumented agents is captured into session Logs. Capture is on by default for new agents. It uses the same [allowlist and per-agent overrides](/app/agent-policy-allowlists) as recording and related policies; when capture is forced on, you can also set a minimum log level. `parlotize(capture_logs=…, log_level=…)` can override Settings for the process.

## Settings → Gen AI content capture

**Settings → Gen AI content capture** controls whether large language model (LLM) message and tool payloads are stored for span detail views. It is on by default and uses the same [allowlist controls](/app/agent-policy-allowlists). `parlotize(capture_genai_content=…)` can override Settings. Turning capture down reduces stored content; turning it up helps debugging but increases sensitivity—pair it with [PII redaction](/app/privacy-redaction).

## Privacy

Captured logs and Gen AI content are subject to your redaction policy. Closed-session UI is designed to show scrubbed text when redaction runs. See [Privacy redaction](/app/privacy-redaction).
