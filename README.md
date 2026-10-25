# Parlot SDK

Parlot shows whether production voice AI agents actually work — turns, handoffs, and goal completion with an evidence trail — not just that the pipeline returned 200s.

Call `parlotize()` once at startup. MIT OpenTelemetry instrumentation for LiveKit Agents (Cloud, self-hosted, or [LiveKit on Telnyx](https://telnyx.com/products/livekit-on-telnyx)), Pipecat, and LangGraph.

**Docs:** [parlot.ai/docs](https://parlot.ai/docs) · **Product:** [parlot.ai](https://parlot.ai)

## Install

```bash
pip install "parlot[livekit]"
# or: pip install "parlot[pipecat]"
# or: pip install "parlot[langgraph]"
# or: pip install "parlot[all]"
```

Or install an instrumentation package directly:

```bash
pip install parlot-instrumentation-livekit
# or: pip install parlot-instrumentation-pipecat
# or: pip install parlot-instrumentation-langgraph
```

## Instrument (LiveKit)

Call `parlotize("…")` before constructing `AgentSession`, then `await ctx.connect()` before `session.start()`:

```python
from parlot.instrumentation.livekit import parlotize

parlotize("my-agent")

from livekit.agents import AgentSession, JobContext, WorkerOptions, cli


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(...)
    await session.start(agent=..., room=ctx.room)
```

## Configure

```bash
export PARLOT_ENDPOINT=https://ingest.parlot.ai
export PARLOT_API_KEY=<org-scoped-key>
```

Mint the API key in Parlot **Settings → API Keys**.

## Next

- [Quick Start](https://parlot.ai/docs/sdk/get-started/quick-start)
- [LiveKit guide](https://parlot.ai/docs/guides/livekit) · example [`examples/livekit/livekit-voice/`](examples/livekit/livekit-voice/)
- [Pipecat guide](https://parlot.ai/docs/guides/pipecat) · example [`examples/pipecat/minimal-voice/`](examples/pipecat/minimal-voice/)
- [LangGraph guide](https://parlot.ai/docs/guides/langgraph) · [`parlot-instrumentation-langgraph`](packages/instrumentation-langgraph/README.md)
- More under [`examples/`](examples/)

## License

Instrumentation packages in this repo are **[MIT](LICENSE)**. The companion analysis platform is **BSL 1.1**: free production use up to 4,000 turns/month for your own agents and agents you operate for clients; above that, or to offer Parlot as a hosted service, requires a commercial license. Each version converts to Apache 2.0 four years after its first public release. Enterprise governance features require an EE license key.

## Development

```bash
uv sync --group dev
uv run pytest -q
```

Use `uv run` from the repo root. Packages: `parlot` · `parlot-core` · `parlot-instrumentation-livekit` · `parlot-instrumentation-langgraph` · `parlot-instrumentation-pipecat`. See [CONTRIBUTING.md](CONTRIBUTING.md).
