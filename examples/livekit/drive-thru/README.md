# drive-thru example

Parlot-instrumented drive-thru ordering agent based on the
[LiveKit drive_thru example](https://github.com/livekit/agents/tree/main/examples/drive_thru).

Keeps full upstream voice behavior (STT/LLM/TTS, ambient `bg_noise.mp3`, cart RPC,
idle nudges) for playground / phone test calls.

Integration requirements (`parlotize()` + `await ctx.connect()`): see
[instrumentation-livekit README](../../../packages/instrumentation-livekit/README.md#instrument).

Recording follows Parlot **Settings → Recording** (telemetry bootstrap). Override per job with `{ "record": true|false }` in dispatch metadata or `parlotize(record=…)` in code.

## Setup

Requires [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/) (`lk`) **v2.19.0+**.

```bash
cd examples/livekit/drive-thru
uv sync
cp .env.example .env
# LIVEKIT_* for Inference; PARLOT_ENDPOINT=https://ingest.parlot.ai + PARLOT_API_KEY
```

## Interactive voice / console

```bash
lk agent console   # Ctrl+T toggles text/audio; lk agent console --text for text-only start
lk agent dev       # LiveKit worker / playground
```

## Agent Simulations

[LiveKit Agent Simulations](https://docs.livekit.io/testing/simulations/) drive a simulated caller from [`sim_scenarios.yaml`](sim_scenarios.yaml) on LiveKit Cloud and grade against `agent_expectations`.

```bash
lk cloud auth   # once
lk agent simulate text --scenarios sim_scenarios.yaml -y
# Recording-quality pass (full STT-LLM-TTS):
lk agent simulate audio --scenarios sim_scenarios.yaml -y
```

Text mode is enough for Parlot turn/tool telemetry. Use audio mode when you need a real session recording.

If simulate fails with `timed out … waiting for the agent to register`, start the worker yourself, then point the sim at it ([LiveKit: run against a live agent](https://docs.livekit.io/testing/simulations/#run-against-a-live-agent)). Use `lk agent start` (not `dev`) so the worker is on the production deployment that `--agent-name` dispatches to. This example has no `agent_name`, so pass an empty string for the project default agent:

```bash
# Terminal 1 — leave running
lk agent start

# Terminal 2
lk agent simulate text --scenarios sim_scenarios.yaml -y --agent-name ""
```

## Legacy: persona_sim

Offline local driver ([`../persona_sim/`](../persona_sim/)). Prefer `lk agent simulate` above.

```bash
uv run python ../persona_sim/run_persona_sim.py --list
uv run python ../persona_sim/run_persona_sim.py --label "Simple Big Mac combo order"
```
