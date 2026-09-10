# hotel-receptionist example

Parlot-instrumented boutique-hotel front desk agent (room bookings, restaurant
reservations, cancellations, invoices, disputes, policy FAQs) backed by an
in-memory SQLite seed database.

Integration requirements (`parlotize()` + `await ctx.connect()` for LiveKit
jobs): see [instrumentation-livekit README](../../packages/instrumentation-livekit/README.md#integration-checklist).

Recording follows Parlot **Settings → Recording** (telemetry bootstrap). Override per job with `{ "record": true|false }` in dispatch metadata or `parlotize(record=…)` in code.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and the [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/) (`lk`).

```bash
cd examples/livekit/hotel-receptionist
uv sync
cp .env.example .env
# edit .env — LIVEKIT_* for Inference; PARLOT_* for ingest
```

Point Parlot at the hosted collector:

```bash
PARLOT_ENDPOINT=https://ingest.parlot.ai
PARLOT_API_KEY=<org key from Settings → API Keys>
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
lk agent console
```

Press **Ctrl+T** to toggle Text/Audio mode, then type as the guest. Press **Q** to quit.

## Persona LLM sample sessions

A second LiveKit Inference LLM role-plays the caller from scenario instructions
(`PERSONA` / `OPENING LINE` / `FACTS` / `DO`). Driver: [`../persona_sim/`](../persona_sim/).
Default scenarios: [`sim_scenarios.yaml`](sim_scenarios.yaml). Full set: [`scenarios.yaml`](scenarios.yaml).

```bash
uv run python ../persona_sim/run_persona_sim.py --list
uv run python ../persona_sim/run_persona_sim.py --label "Simple room booking by phone"
uv run python ../persona_sim/run_persona_sim.py --all --max-turns 24
uv run python ../persona_sim/run_persona_sim.py --scenarios scenarios.yaml --tag feature=room_booking --limit 3
```

Each run prints `parlot_session_id=…`.

## LiveKit playground / worker

```bash
lk agent dev
```

## Architecture

```
agent.py             — HotelReceptionistAgent + Parlot parlotize()
sim_adapter.py       — hooks for shared persona-sim driver
../persona_sim/      — shared persona-LLM guest + AgentSession.run() driver
sim_scenarios.yaml   — curated PERSONA scenarios (default)
scenarios.yaml       — full LiveKit simulation scenario set
tools_*.py           — rooms / restaurant / services tools
book_*.py            — AgentTask booking flows
hotel_db.py          — HotelDB (apsw) + schema + pricing
fake_data/seed.py    — seed builders (in-memory bytes + optional .db file)
```
