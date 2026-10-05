---
title: Evaluations
description: Built-in session quality signals and custom LLM-as-judge evaluations.
---

# Evaluations

Parlot evaluates sessions in two complementary ways: automatic signals at session close, and **custom evaluations** you define under **Evals**.

## Built-in close-time signals

When a session closes, Parlot can run quality pipelines such as:

- Goal lifecycle (did the agent fulfill the caller’s intent?)
- Sentiment over turns
- Topic classification
- Disengagement or related quality flags

Results surface on the session shell (Overview / Latency analysis areas) and in fleet views. Built-ins do not replace custom judges; they provide a baseline without configuration.

## Custom evaluations (`/evals`)

Use custom evaluations when you need your own rubric—compliance phrases, brand tone, and any custom criteria.

Typical workflow:

1. Open **Evals** and create a definition (`/evals/new`).
2. Write criteria in plain language and choose a scoring approach.
3. Connect a model under **Settings → LLM Connections** (bring-your-own-key) so judges can run.
4. Run the evaluation over a session set and inspect runs under `/evals/:evalId/runs` or `/evals/runs/:runId`.

Plan limits may cap how many custom definitions you can store. See [Licensing and plans](/app/licensing-and-plans) and Settings → Billing for your workspace entitlements.

## Event-driven evaluations

On paid plans, custom judges can run automatically when a session closes. Free workspaces can still create evaluations and run them manually—automatic session-close rules require a paid plan. The Evals page explains when that option is unavailable; see also [Licensing and plans](/app/licensing-and-plans).

## Tips

- Prefer redacted transcripts for judges; Parlot’s close pipeline is built so judges see scrubbed text when redaction succeeds.
- Start with a small historical sample before enabling broad automatic runs.
- Tie failing scores back to [Timeline](/app/timeline) evidence turns.
