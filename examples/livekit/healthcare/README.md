# healthcare example

Parlot-instrumented medical front-desk agent (intake, appointments, billing) based on
the [LiveKit healthcare example](https://github.com/livekit/agents/tree/main/examples/healthcare).

Keeps full upstream voice behavior (STT/LLM/TTS, AgentTasks, idle nudges) plus optional
SIP warm-transfer for human escalation on live calls. Persona sims stay in-bot and do
not require SIP.

Integration requirements (`parlotize()` + `await ctx.connect()`): see
[instrumentation-livekit README](../../../packages/instrumentation-livekit/README.md#instrument).

Recording follows Parlot **Settings → Recording** (telemetry bootstrap). Override per job with `{ "record": true|false }` in dispatch metadata or `parlotize(record=…)` in code.

## Setup

```bash
cd examples/livekit/healthcare
uv sync
cp .env.example .env
# LIVEKIT_* for Inference; PARLOT_ENDPOINT=https://ingest.parlot.ai + PARLOT_API_KEY
```

For live warm-transfer, also set `LIVEKIT_SIP_OUTBOUND_TRUNK`,
`LIVEKIT_SUPERVISOR_DESTINATION`, and `LIVEKIT_SIP_NUMBER`.

### Softphone (Zoiper) instead of cell PSTN

Zoiper does **not** register to LiveKit. Register it to your **SIP carrier**
(typically Telnyx), then have LiveKit dial that destination through the outbound trunk:

1. Telnyx: create a **Credential** SIP connection + username/password; assign a DID (or use the SIP user URI).
2. Zoiper (iPhone): account → domain `sip.telnyx.com`, same username/password; confirm registered.
3. LiveKit: outbound trunk pointing at Telnyx (`ST_…`) — same as PSTN setup.
4. Healthcare `.env`:
   - `LIVEKIT_SIP_OUTBOUND_TRUNK=ST_…`
   - `LIVEKIT_SUPERVISOR_DESTINATION=+1…` (DID that rings Zoiper), **or**
     `sip:<username>@sip.telnyx.com`
   - `LIVEKIT_SIP_NUMBER=+1…` (caller ID on the outbound leg)

Ask the agent for a human; Zoiper should ring. You still need the LiveKit↔Telnyx
outbound trunk — the softphone only replaces the supervisor’s cell as the dial target.

## Interactive voice / console

The worker registers as dispatch name `healthcare` (see `agent_name=` in
`agent.py`). That avoids auto-dispatch into WarmTransferTask’s
`{room}-human-agent` briefing room. `lk agent console` still works locally;
Cloud playground / SIP / tokens must dispatch that name explicitly.

```bash
lk agent console   # Ctrl+T toggles text/audio; lk agent console --text for text-only start
lk agent dev       # LiveKit worker — playground must select agent "healthcare"
# Example explicit dispatch / join token:
lk dispatch create --agent-name healthcare --room my-room
lk token create --identity user --room my-room --agent healthcare --join
```

For inbound SIP, set the dispatch rule’s `room_config.agents` to
`agent_name: healthcare`.

## Persona LLM sample sessions

Shared driver: [`../persona_sim/`](../persona_sim/).

```bash
uv run python ../persona_sim/run_persona_sim.py --list
uv run python ../persona_sim/run_persona_sim.py --label "Returning patient books appointment"
uv run python ../persona_sim/run_persona_sim.py --all --max-turns 24
```

Each run prints `parlot_session_id=…`.
