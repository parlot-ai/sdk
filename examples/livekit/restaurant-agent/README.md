# restaurant-agent example

Parlot-instrumented restaurant routing: greeter hands off to reservation, takeaway, or checkout specialists.

Uses LiveKit Inference for STT/LLM/TTS (no separate provider API keys required when using LiveKit Cloud inference).

Integration requirements (`parlotize()` + `await ctx.connect()`): see [instrumentation-livekit README](../../../packages/instrumentation-livekit/README.md#instrument).

Recording follows Parlot **Settings → Recording** (telemetry bootstrap). Override per job with `{ "record": true|false }` in dispatch metadata or `parlotize(record=…)` in code.

## Setup

Requires [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/) (`lk`) **v2.19.0+**.

```bash
cd examples/livekit/restaurant-agent
uv sync
cp .env.example .env
# edit .env — LIVEKIT_* and PARLOT_*
```

## Run

```bash
lk agent console
lk agent dev
```

Agent handoffs (greeter → reservation/takeaway/checkout) appear in Parlot telemetry.

## Agent Simulations

[LiveKit Agent Simulations](https://docs.livekit.io/testing/simulations/) drive a simulated diner from [`sim_scenarios.yaml`](sim_scenarios.yaml):

```bash
lk cloud auth   # once
lk agent simulate text --scenarios sim_scenarios.yaml -y
lk agent simulate audio --scenarios sim_scenarios.yaml -y
```

If simulate fails with `timed out … waiting for the agent to register`, start the worker yourself, then point the sim at it ([LiveKit: run against a live agent](https://docs.livekit.io/testing/simulations/#run-against-a-live-agent)). Use `lk agent start` (not `dev`) so the worker is on the production deployment that `--agent-name` dispatches to. This example has no `agent_name`, so pass an empty string for the project default agent:

```bash
# Terminal 1 — leave running
lk agent start

# Terminal 2
lk agent simulate text --scenarios sim_scenarios.yaml -y --agent-name ""
```
