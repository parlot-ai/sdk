---
title: Privacy redaction
description: How Parlot removes personally identifiable information from transcripts and recordings.
---

# Privacy redaction

**Settings → PII redaction** controls how Parlot handles personally identifiable information (PII) in conversational data. Redaction is on by default for new agents.

## What redaction does

Parlot scrubs sensitive details such as names, addresses, dates of birth, phone numbers, emails, and secrets from stored transcripts and related content. Masked tokens (for example `[PERSON]` or `[EMAIL]`) replace identified spans so dashboards and judges can still read structure without raw identifiers.

Recording policies can also beep or mute sensitive audio segments when that pipeline is enabled for your deployment.

PII redaction is **experimental**. It can miss sensitive details or mis-label ordinary text. Treat redacted output as a best-effort aid, not a guarantee of full compliance. Before you export, share, or otherwise move data out of Parlot, review the content yourself and confirm it meets your legal and policy requirements.

## Fail-closed behavior

The product copy matches the intended policy: if redaction cannot be completed, Parlot does **not** show the raw data. That fail-closed / withhold behavior protects healthcare and financial contexts when the privacy filter is unavailable or errors.

Scrubbing still aims to run for closed sessions used in analytics; the setting’s critical effect is whether incomplete work is withheld from viewers rather than shown unredacted.

## Agent allowlists

When the settings page exposes per-agent controls, you can keep organization defaults and override individual agents. New agents inherit the default until you change them.

## Where you see results

After a session closes and redaction finishes:

- Timeline and analysis views show scrubbed transcript text
- Evaluation judges consume redacted text
- Exports reflect the same protected content

See also [Session logs and capture](/app/session-logs) and [Recording](/app/recording).
