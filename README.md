# Parlot SDK

Open-source SDK and instrumentation libraries for the Parlot.ai multi-agent observability platform.

## Structure

- `packages/core/` — semantic conventions, base processor, UUID v7 session ids
- `packages/instrumentation-livekit/` — LiveKit Agents OTel instrumentation (own `pyproject.toml`, `CHANGELOG.md`)

## Local dev with platform collector

Point the agent at the platform OTLP receiver (no path suffix — the SDK appends `/v1/traces` and `/v1/metrics`):

```bash
export PARLOT_ENDPOINT=http://localhost:4318
```

Full stack (ClickHouse, collector, API, agent, resolve): [platform README — Local E2E runbook](../platform/README.md#local-e2e-runbook-dev-onboarding).
