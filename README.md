# Parlot SDK

Open-source ([MIT](LICENSE)) Python SDK and instrumentation libraries for the [Parlot.ai](https://parlot.ai) AI agent observability platform.

**Contributing / releases:** see [CONTRIBUTING.md](CONTRIBUTING.md) (PR-only `main`, conventional PR titles, Release Please).

**Docs:** see the [documentation site](./docs/) (`cd docs && bun start`) or [parlot.ai/docs](https://parlot.ai/docs) — Quick Start, concepts, and LiveKit guides.

## Installation

Install the framework-specific instrumentation package via PyPI:

### LiveKit Agents

```bash
# Using pip
pip install parlot-instrumentation-livekit

# Or with uv
uv add parlot-instrumentation-livekit

# Or via the parlot meta-package
pip install "parlot[livekit]"
```

### LangGraph / LangChain Agents

```bash
# Using pip
pip install parlot-instrumentation-langgraph

# Or with uv
uv add parlot-instrumentation-langgraph

# Or via the parlot meta-package
pip install "parlot[langgraph]"
```

## Structure

- `packages/meta/` — `parlot` meta-package with framework extras
- `packages/core/` — semantic conventions (OTel GenAI v1.41 + Conversation Contract + voice), base processor, UUID v7 session ids
- `packages/instrumentation-livekit/` — LiveKit Agents OTel instrumentation
- `packages/instrumentation-langgraph/` — LangGraph / LangChain `configure()` instrumentation

## Examples

| Example | Description | Parlot install |
|---------|-------------|----------------|
| [`examples/livekit/livekit-voice/`](examples/livekit/livekit-voice/) | Minimal hello-world LiveKit agent | Path (monorepo dev) |
| [`examples/livekit/multi-agent/`](examples/livekit/multi-agent/) | Storytelling with agent handoffs | Path (monorepo dev) |
| [`examples/livekit/restaurant-agent/`](examples/livekit/restaurant-agent/) | Restaurant greeter → specialist routing | Path (monorepo dev) |
| [`examples/livekit/hotel-receptionist/`](examples/livekit/hotel-receptionist/) | Boutique-hotel receptionist + persona sample sessions | Path (monorepo dev) |
| [`examples/livekit/healthcare/`](examples/livekit/healthcare/) | Medical front desk (intake, appointments, billing) + persona sims | Path (monorepo dev) |
| [`examples/livekit/drive-thru/`](examples/livekit/drive-thru/) | Drive-thru ordering with dynamic tools + persona sims | Path (monorepo dev) |
| [`examples/livekit/persona_sim/`](examples/livekit/persona_sim/) | Shared persona-LLM text session driver for LiveKit examples | — |
| [`examples/langgraph/minimal-agent/`](examples/langgraph/minimal-agent/) | Standalone LangGraph + `configure()` | Path (monorepo dev) |

Integration requirements: [instrumentation-livekit README](packages/instrumentation-livekit/README.md#integration-checklist), [instrumentation-langgraph README](packages/instrumentation-langgraph/README.md).

## Local Development

From the SDK workspace root:

```bash
cd sdk
uv sync --group dev
uv run pytest -q
```

Individual packages are workspace members — use `uv run` from the repo root rather than `pip install` / bare `python -m pytest`.

## Agent Deployment Version

Parlot stamps `gen_ai.agent.version` on each session when a deployment version is configured. This powers version tracking on the Agents portfolio and per-session attributes in the platform UI.

### Resolution Order

`configure(version=...)` resolves once at startup (first non-empty wins):

1. `version=` kwarg passed to `configure()`
2. `__version__` or `VERSION` on the agent entry module (`__main__`)
3. `PARLOT_AGENT_VERSION` environment variable (runtime override)
4. Local git short SHA when a `.git` directory is present (dev convenience only)

If none resolve, the attribute is omitted.

### Recommended Patterns

- **Example / single-file agents:** set `__version__ = "1.2.3"` at the top of your entrypoint and bump on release. See [`examples/livekit/restaurant-agent/agent.py`](examples/livekit/restaurant-agent/agent.py).
- **Runtime override:** set `PARLOT_AGENT_VERSION` when the deploy label must differ from the code's `__version__` (canary, injected build metadata).
- **Explicit:** pass `configure(version="2026.03.26")` for tests or special cases.

CI commit env vars (`GITHUB_SHA`, etc.) and installed package metadata are **not** consulted — they are unreliable in production containers.

### LiveKit Caveat

Under LiveKit `dev` / spawned `job_proc` workers, `__main__` is often not your agent file, so `__version__` on the entrypoint may not resolve. Prefer `configure(version=...)` or `PARLOT_AGENT_VERSION`. See [instrumentation-livekit README — What to expect for version](packages/instrumentation-livekit/README.md#what-to-expect-for-version).

## Local Dev with Platform Collector

Point the agent at the platform OTLP receiver (no path suffix — the SDK appends `/v1/traces` and `/v1/metrics`):

```bash
export PARLOT_ENDPOINT=http://localhost:4318
# Mint in Parlot Settings → API Keys (or POST /v1/settings/api-keys), then:
export PARLOT_API_KEY=<minted-org-key>
```

Full stack (collector, API, agent, resolve): [platform Local E2E runbook](https://github.com/parlot-ai/platform#local-e2e-runbook-dev-onboarding) (§6a mint key).
