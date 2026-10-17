# hotel-receptionist example

Parlot-instrumented boutique-hotel front desk agent (room bookings, restaurant
reservations, cancellations, invoices, disputes, policy FAQs) backed by an
in-memory SQLite seed database.

Integration requirements (`parlotize()` + `await ctx.connect()` for LiveKit
jobs): see [instrumentation-livekit README](../../../packages/instrumentation-livekit/README.md#instrument).

Recording follows Parlot **Settings → Recording** (telemetry bootstrap). Override per job with `{ "record": true|false }` in dispatch metadata or `parlotize(record=…)` in code.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and the [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/) (`lk`) **v2.19.0+**.

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

## Agent Simulations

[LiveKit Agent Simulations](https://docs.livekit.io/testing/simulations/) run an LLM-driven simulated caller against this agent on LiveKit Cloud, then judge the transcript against `agent_expectations`. Default scenarios: [`sim_scenarios.yaml`](sim_scenarios.yaml). Full set: [`scenarios.yaml`](scenarios.yaml).

Authenticate the CLI once (`lk cloud auth`), then from this directory:

```bash
lk agent simulate text --scenarios sim_scenarios.yaml -y
# Optional: full STT-LLM-TTS pipeline + call-quality metrics (needed for useful Parlot audio)
lk agent simulate audio --scenarios sim_scenarios.yaml -y
# Full suite:
lk agent simulate text --scenarios scenarios.yaml -y
```

Text mode exercises LLM, tools, and conversation logic (Parlot telemetry). Audio mode also exercises STT/TTS and is what you want when verifying session recordings in Parlot. The CLI may mint scenario `id` fields in place on first run (`-y` confirms).

## LiveKit playground / worker

```bash
lk agent dev
```

## Legacy: persona_sim

Offline local driver ([`../persona_sim/`](../persona_sim/)) that drives `AgentSession.run()` without LiveKit Cloud. Prefer `lk agent simulate` above for Cloud sims and sample data.

```bash
uv run python ../persona_sim/run_persona_sim.py --list
uv run python ../persona_sim/run_persona_sim.py --label "Simple room booking by phone"
```

## Architecture

```
agent.py             — HotelReceptionistAgent + Parlot parlotize()
sim_scenarios.yaml   — curated LiveKit Agent Simulation scenarios
scenarios.yaml       — full LiveKit simulation scenario set
sim_adapter.py       — hooks for legacy persona-sim driver
../persona_sim/      — legacy offline persona-LLM driver
tools_*.py           — rooms / restaurant / services tools
book_*.py            — AgentTask booking flows
hotel_db.py          — HotelDB (apsw) + schema + pricing
fake_data/seed.py    — seed builders (in-memory bytes + optional .db file)
```
