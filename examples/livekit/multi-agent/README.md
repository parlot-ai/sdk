# multi-agent example

Parlot-instrumented multi-agent storytelling: IntroAgent collects name and location, then hands off to StoryAgent (OpenAI Realtime) for a personalized interactive story.

Integration requirements (`parlotize()` + `await ctx.connect()`): see [instrumentation-livekit README](../../../packages/instrumentation-livekit/README.md#instrument).

## Setup

Requires [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/) (`lk`) **v2.19.0+**.

```bash
cd examples/livekit/multi-agent
uv sync
cp .env.example .env
# edit .env — LIVEKIT_*, OPENAI / provider keys as needed, PARLOT_*
```

## Run

```bash
lk agent console
lk agent dev
```

Handoffs from IntroAgent → StoryAgent appear in Parlot as agent handoff spans.

## Agent Simulations

[LiveKit Agent Simulations](https://docs.livekit.io/testing/simulations/) drive a simulated listener from [`sim_scenarios.yaml`](sim_scenarios.yaml):

```bash
lk cloud auth   # once
lk agent simulate text --scenarios sim_scenarios.yaml -y
lk agent simulate audio --scenarios sim_scenarios.yaml -y
```
