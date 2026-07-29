# hotel-receptionist example

Parlot-instrumented boutique-hotel front desk agent (room bookings, restaurant
reservations, cancellations, invoices, disputes, policy FAQs) backed by an
in-memory SQLite seed database.

Integration requirements (`configure()` + `await ctx.connect()` for LiveKit
jobs): see [instrumentation-livekit README](../../packages/instrumentation-livekit/README.md#integration-checklist).

Recording is **off** (`configure(..., record=False)`) — telemetry only.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
cd sdk/examples/hotel-receptionist
uv sync
cp .env.example .env
# edit .env — LIVEKIT_* for Inference; PARLOT_* for the collector
```

For local platform ingest verification, point Parlot at the collector:

```bash
PARLOT_ENDPOINT=http://localhost:4318
PARLOT_API_KEY=<minted key from Parlot Settings → API Keys>
```

Optional seed DB file for inspection:

```bash
uv run python fake_data/seed.py
```

Stable anchors (seed date `2026-06-08`):

| Guest / reservation | Code |
|---------------------|------|
| Eleanor Smith (upcoming stay) | `HTL-AB12` |
| Sofía García (in-house) | `HTL-EF56` |
| Hannah Kowalski (dinner tonight) | `RES-LM12` |

## Interactive (console)

```bash
uv run python agent.py console
```

Press **Ctrl+T** to toggle Text/Audio mode, then type as the guest. Press **Q** to quit.

## Persona LLM sample sessions

The only automated session path. A second LiveKit Inference LLM role-plays the
caller from scenario instructions (`PERSONA` / `OPENING LINE` / `FACTS` /
`DO`). Default scenarios: [`sim_scenarios.yaml`](sim_scenarios.yaml) (curated
subset). Full set: [`scenarios.yaml`](scenarios.yaml).

```bash
uv run python run_persona_sim.py --list
uv run python run_persona_sim.py --label "Simple room booking by phone"
uv run python run_persona_sim.py --all --max-turns 24
uv run python run_persona_sim.py --scenarios scenarios.yaml --tag feature=room_booking --limit 3
```

Each run prints `parlot_session_id=…`. Verify close/ingest before the next scenario:

```bash
uv run python verify_ingest.py <parlot_session_id>
```

Needs `DATABASE_URL` + `TINYBIRD_TOKEN` in this example's `.env`, or set
`PLATFORM_ENV_FILE` to a platform `.env.local` when verifying a local stack.
Longer calls can take ~60–90s for session-close goal/sentiment steps.

Checks:

1. Postgres: `session_hot_meta.session_open = false`; `session_close_runs.status = completed`
2. Tinybird: `sessions` row; `session_spans` present; `session_recordings` empty

## LiveKit playground / worker

```bash
uv run python agent.py dev
```

## Architecture

```
agent.py             — HotelReceptionistAgent + Parlot configure(record=False)
run_persona_sim.py   — persona-LLM guest + AgentSession.run() driver
sim_scenarios.yaml   — curated PERSONA scenarios (default)
scenarios.yaml       — full LiveKit simulation scenario set
verify_ingest.py     — Postgres + Tinybird session-close checks
tools_*.py           — rooms / restaurant / services tools
book_*.py            — AgentTask booking flows
hotel_db.py          — HotelDB (apsw) + schema + pricing
fake_data/seed.py    — seed builders (in-memory bytes + optional .db file)
```
