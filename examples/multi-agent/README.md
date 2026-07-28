# multi-agent example

Parlot-instrumented multi-agent storytelling: IntroAgent collects name and location, then hands off to StoryAgent (OpenAI Realtime) for a personalized interactive story.

Integration requirements (`configure()` + `await ctx.connect()`): see [instrumentation-livekit README](../../packages/instrumentation-livekit/README.md#integration-checklist).

## Setup

Requires [uv](https://docs.astral.sh/uv/) and read access to the private `parlot-ai/sdk` repo (git-tag install).

```bash
cd sdk/examples/multi-agent
uv sync
cp .env.example .env
# edit .env
```

### SDK contributors (monorepo dev)

Replace `[tool.uv.sources]` in `pyproject.toml` with path overrides:

```toml
parlot-core = { path = "../../packages/core", editable = true }
parlot-instrumentation-livekit = { path = "../../packages/instrumentation-livekit", editable = true }
```

Then `uv sync` again.

## Run

```bash
uv run python agent.py dev
```

Handoffs from IntroAgent → StoryAgent appear in Parlot as agent handoff spans.
