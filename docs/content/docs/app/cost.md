---
title: Cost
description: Session spend and workspace Cost & margin for rates and margin.
---

# Cost

Parlot shows spend in two places:

- **Session Cost** (`/sessions/:sessionId/cost`) — estimated spend for one conversation after usage attributes are available
- **Cost & margin** (`/cost`) — workspace rate card and margin trends under Observe

## What is included

Costs typically combine:

- Large language model (LLM) token usage
- Speech-to-text (STT) and text-to-speech (TTS) usage when reported
- Aggregated session totals used in Overview and agent cost views

Figures depend on rates configured for your organization. If a model has no rate, amounts may be missing or incomplete until you update the rate card.

## Cost & margin

Open **Observe → Cost & margin** to:

- Review provider rates that feed cost views (Rate card tab)
- Add or adjust model rates (including contract rates)
- Inspect recent margin when sessions have closed with cost attributes (Margin & cost tab)

Unpriced models surface a warning on cost views and a badge on the Cost & margin nav item. This is separate from **Plan & billing** (your Parlot subscription under Settings).

See [Organization settings](/app/organization-settings#cost--margin) for related workspace settings.

## Fleet context

Use [Overview](/app/overview) and the agent workspace Cost tab for trends. Use the session Cost tab when you need the bill of materials for one interaction.
