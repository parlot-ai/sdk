# multi-agent example

Parlot-instrumented multi-agent storytelling: IntroAgent collects name and location, then hands off to StoryAgent (OpenAI Realtime) for a personalized interactive story.

Integration requirements (`configure()` + `await ctx.connect()`): see [instrumentation-livekit README](../../packages/instrumentation-livekit/README.md#integration-checklist).

## Setup
 
```bash
cd examples/livekit/multi-agent
uv sync
cp .env.example .env
# edit .env
```

## Run

```bash
uv run python agent.py dev
```

Handoffs from IntroAgent → StoryAgent appear in Parlot as agent handoff spans.
