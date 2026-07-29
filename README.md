# Parlot SDK

Open-source ([MIT](LICENSE)) SDK and instrumentation libraries for the Parlot.ai multi-agent observability platform.

**Docs:** see the [documentation site](./docs/) (`cd docs && bun start`) — Quick Start, concepts, and LiveKit guides.

## Structure

- `packages/core/` — semantic conventions, base processor, UUID v7 session ids
- `packages/instrumentation-livekit/` — LiveKit Agents OTel instrumentation (own `pyproject.toml`, `CHANGELOG.md`)

## Examples

| Example | Description | Parlot install |
|---------|-------------|----------------|
| [`examples/livekit-voice/`](examples/livekit-voice/) | Minimal hello-world agent | Path (monorepo dev) |
| [`examples/multi-agent/`](examples/multi-agent/) | Storytelling with agent handoffs | Git tag |
| [`examples/restaurant-agent/`](examples/restaurant-agent/) | Restaurant greeter → specialist routing | Git tag |
| [`examples/hotel-receptionist/`](examples/hotel-receptionist/) | Boutique-hotel receptionist + seed sample sessions | Path (monorepo dev) |

Integration requirements for all examples: [instrumentation-livekit README](packages/instrumentation-livekit/README.md#integration-checklist).

### Install from git

```toml
# Consumer pyproject.toml
[tool.uv.sources]
parlot-core = { git = "https://github.com/parlot-ai/sdk.git", subdirectory = "packages/core", tag = "v0.1.0" }
parlot-instrumentation-livekit = { git = "https://github.com/parlot-ai/sdk.git", subdirectory = "packages/instrumentation-livekit", tag = "v0.1.0" }
```

- `uv lock` pins the commit SHA.
- Tag both `parlot-core` and `parlot-instrumentation-livekit` at the same release (instrumentation depends on core).

See `examples/multi-agent/` or `examples/restaurant-agent/` for full consumer `pyproject.toml` templates.

## Local dev

From the SDK workspace root:

```bash
cd sdk
uv sync --group dev
uv run pytest -q
```

Individual packages (e.g. `packages/instrumentation-livekit`) are workspace members — use `uv run` from the repo root rather than `pip install` / bare `python -m pytest`.

## Agent deployment version

Parlot stamps `gen_ai.agent.version` on each session when a deployment version is configured. This powers version tracking on the Agents portfolio and per-session attributes in the platform UI.

### Resolution order

`configure(version=...)` resolves once at startup (first non-empty wins):

1. `version=` kwarg passed to `configure()`
2. `__version__` or `VERSION` on the agent entry module (`__main__`)
3. `PARLOT_AGENT_VERSION` environment variable (runtime override)
4. Local git short SHA when a `.git` directory is present (dev convenience only)

If none resolve, the attribute is omitted.

### Recommended patterns

- **Example / single-file agents:** set `__version__ = "1.2.3"` at the top of your entrypoint and bump on release. See [`examples/restaurant-agent/agent.py`](examples/restaurant-agent/agent.py).
- **Runtime override:** set `PARLOT_AGENT_VERSION` when the deploy label must differ from the code's `__version__` (canary, injected build metadata).
- **Explicit:** pass `configure(version="2026.03.26")` for tests or special cases.

CI commit env vars (`GITHUB_SHA`, etc.) and installed package metadata are **not** consulted — they are unreliable in production containers.

### LiveKit caveat

Under LiveKit `dev` / spawned `job_proc` workers, `__main__` is often not your agent file, so `__version__` on the entrypoint may not resolve. Prefer `configure(version=...)` or `PARLOT_AGENT_VERSION`. See [instrumentation-livekit README — What to expect for version](packages/instrumentation-livekit/README.md#what-to-expect-for-version).

## Local dev with platform collector

Point the agent at the platform OTLP receiver (no path suffix — the SDK appends `/v1/traces` and `/v1/metrics`):

```bash
export PARLOT_ENDPOINT=http://localhost:4318
# Mint in Parlot Settings → API Keys (or POST /v1/settings/api-keys), then:
export PARLOT_API_KEY=<minted-org-key>
```

Full stack (collector, API, agent, resolve): [platform Local E2E runbook](https://github.com/parlot-ai/platform#local-e2e-runbook-dev-onboarding) (§6a mint key).
