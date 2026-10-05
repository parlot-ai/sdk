---
title: Privacy redaction
description: How Parlot removes personally identifiable information from transcripts and recordings.
---

# Privacy redaction

**Settings → PII redaction** controls how Parlot handles personally identifiable information (PII) in conversational data. Redaction is on by default for new agents.

## What redaction does

Parlot scrubs sensitive details such as names, addresses, dates of birth, phone numbers, emails, and secrets from stored transcripts and related content. Masked tokens (for example `[PERSON]` or `[EMAIL]`) replace identified spans so dashboards and judges can still read structure without raw identifiers.

When recordings are stored, Parlot also beeps out those sensitive spans in the audio so the sanitized recording matches the scrubbed transcript.

PII redaction is **experimental**. It can miss sensitive details or mis-label ordinary text. Treat redacted output as a best-effort aid, not a guarantee of full compliance. Before you export, share, or otherwise move data out of Parlot, review the content yourself and confirm it meets your legal and policy requirements.

## When redaction fails

If redaction cannot finish, Parlot **withholds** the content instead of showing the raw transcript or recording. You may see messages such as “Content withheld — redaction unavailable” or “Recording withheld (PII redaction).” Unredacted content is never shown.

Redaction still runs for closed sessions used in analytics. The setting’s critical effect is this withhold behavior when scrubbing fails or is unavailable.

## Agent allowlists

Which agents get PII redaction uses the same **New agents** allowlist and **Known agents** overrides as recording, logs, and Gen AI content capture. See [Agent policy allowlists](/app/agent-policy-allowlists) for how those controls work and common setups. Unlike those capture policies, PII redaction has **no** `parlotize()` override—it is applied in Parlot from Settings only.

PII redaction defaults to on for new agents (`*` allowlist).

## Where you see results

After a session closes and redaction finishes:

- Timeline and analysis views show scrubbed transcript text
- Evaluation judges consume redacted text
- Exports reflect the same protected content

See also [Agent policy allowlists](/app/agent-policy-allowlists), [Session logs and capture](/app/session-logs), and [Recording](/app/recording).
