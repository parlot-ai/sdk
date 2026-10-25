# livekit-voice

Minimal LiveKit voice agent with Parlot. Talk through the playground, then open Parlot to see the session — turns, waterfall, and usage.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/) (`lk`) **v2.19.0+**
- LiveKit project credentials (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`)
- OpenAI API key
- Parlot API key (mint in **Settings → API Keys**)

## Run

```bash
cd examples/livekit/livekit-voice
uv sync
cp .env.example .env
# fill LIVEKIT_*, OPENAI_API_KEY, PARLOT_API_KEY
lk agent console
lk agent dev
```

When a job connects, the session appears in Parlot.

## Agent Simulations

[LiveKit Agent Simulations](https://docs.livekit.io/testing/simulations/) drive a simulated user from [`sim_scenarios.yaml`](sim_scenarios.yaml):

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

## What Parlot adds

In `agent.py`, instrumentation is two required calls:

1. `parlotize("livekit-voice")` before building `AgentSession`
2. `await ctx.connect()` before `session.start()`

Remove those and the agent still works — just without telemetry.

## Next

- [LiveKit guide](https://parlot.ai/docs/guides/livekit) — recording, identity, and more options
- More examples under [`examples/livekit/`](../)
