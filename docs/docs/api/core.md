---
title: Core & Session API
description: API reference for parlot-core semantic conventions, metadata, platform refs, and session helpers.
sidebar_position: 4
sidebar_custom_props:
  eyebrow: Shared
---

# Core & Session API Reference

`parlot-core` contains framework-agnostic session helpers, OpenTelemetry semantic conventions, and state context management.

These functions can be imported from `parlot.core` or directly from framework packages (`parlot.instrumentation.livekit` and `parlot.instrumentation.langgraph`).

---

## Session Metadata & Custom Attributes

### `set_session_metadata()`

```python
def set_session_metadata(**pairs: str | int | float | bool) -> None
```

Attaches custom key/value metadata pairs to the active Parlot session.

Each keyword becomes an attribute named `session.metadata.<name>` on the active `parlot.session` span and is preserved through `parlot.session.close`. These fields appear in session detail and filter views in the Parlot platform UI.

#### Example

```python
from parlot.core import set_session_metadata

set_session_metadata(
    order_id="12345",
    crm_account_id="ACC-99",
    priority=1,
    is_vip=True,
)
```

---

### `set_session_attribute()`

```python
def set_session_attribute(key: str, value: str | int | float | bool) -> None
```

Stamps a single custom attribute on the active session under `session.metadata.<key>`.

#### Parameters

- `key` (`str`): Attribute name. If not prefixed with `session.metadata.`, the prefix is added automatically.
- `value` (`str | int | float | bool`): Value to record.

#### Example

```python
from parlot.core import set_session_attribute

set_session_attribute("cart_total_usd", 149.99)
```

---

## Platform References & Search Linking

### `add_platform_ref()`

```python
def add_platform_ref(
    kind: str,
    value: str,
    *,
    framework: str = "custom",
) -> None
```

Attaches an external searchable identifier to the active Parlot session span.

Stamps `platform.ref.<kind> = <value>` and establishes canonical `platform.ref.framework / kind / value` attributes. This enables searching, resolving, and deeplinking sessions by external identifiers (e.g. CRM ticket, payment reference, support case).

#### Parameters

- `kind` (`str`): Identifier type (e.g. `"crm_ticket"`, `"order_number"`, `"call_sid"`).
- `value` (`str`): Unique identifier value (e.g. `"TKT-9921"`, `"CA12345678"`).
- `framework` (`str`, optional): Originating framework name. Defaults to `"custom"`.

#### Example

```python
from parlot.core import add_platform_ref

add_platform_ref("crm_ticket", "TKT-8841")
add_platform_ref("stripe_customer_id", "cus_N9a8bc")
```

---

### `stamp_platform_refs()`

```python
def stamp_platform_refs(
    span: Span,
    refs: list[tuple[str, str, str]],
) -> None
```

Low-level helper to stamp a list of `(framework, kind, value)` tuples onto any OpenTelemetry span.

---

## Human Escalation & Roles

### `record_human_rep()`

```python
def record_human_rep(participant_id: str, *, label: Optional[str] = None) -> None
```

Marks a participant as a human representative (`human_rep`).

Stamps `session.topology.agents` on the session span and ensures that subsequent voice or text turns from `participant_id` are recorded with `turn.participant_role = "human_rep"`.

#### Parameters

- `participant_id` (`str`): The participant identifier within the room/session.
- `label` (`str`, optional): Human-readable name or label (e.g. `"Tier 2 Escalation Desk"`).

#### Example

```python
from parlot.core import record_human_rep

record_human_rep("agent_sarah_102", label="Senior Specialist")
```

---

### `human_escalation()`

```python
@contextmanager
def human_escalation(label: Optional[str] = None) -> Iterator[None]
```

Context manager that marks the next participant joining the active session as a human representative.

#### Parameters

- `label` (`str`, optional): Optional role or team label for the incoming human representative.

#### Example

```python
from parlot.core import human_escalation

async def transfer_call(dial_helper, target_number):
    with human_escalation(label="Escalations"):
        await dial_helper.dial(target_number)
```

---

## Session Context & State Access

Parlot tracks session state in thread/async-safe `contextvars`.

### `get_active_session()`

```python
def get_active_session() -> Optional[SessionState]
```

Returns the current `SessionState` bound to the active context, or `None` if outside an instrumented session.

---

### `get_active_session_span()`

```python
def get_active_session_span() -> Optional[Span]
```

Returns the active `parlot.session` OpenTelemetry `Span` for the current context, or `None`.

---

### `session_owned()`

```python
def session_owned(*, framework: Optional[str] = None) -> bool
```

Returns `True` if an active session with a valid `session.id` is currently bound in context.

#### Parameters

- `framework` (`str`, optional): If provided, checks whether the active session is owned by that specific framework (e.g. `session_owned(framework="livekit")`).

---

### `SessionState`

```python
@dataclass
class SessionState:
    session_id: str = ""
    room_name: str = ""
    room_sid: str = ""
    agent_label: str = ""
    turn_count: int = 0
    tool_call_count: int = 0
    handoff_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    human_rep_participant_ids: set[str] = field(default_factory=set)
    topology_agents: list[dict[str, Any]] = field(default_factory=list)
    custom_metadata: dict[str, str] = field(default_factory=dict)
    framework: str = ""
```

---

## Semantic Convention Constants (`parlot.core.attrs`)

`parlot.core.attrs` exports all attribute, span, and metric name constants:

### Spans (`CONTRACT_SPAN_NAMES`)

```python
SPAN_CONVERSATION_SESSION = "parlot.session"
SPAN_PARLOT_TURN          = "parlot.turn"
SPAN_PARLOT_SESSION_CLOSE = "parlot.session.close"
SPAN_AGENT_HANDOFF        = "parlot.agent.handoff"

# Voice Operational Spans
SPAN_VOICE_TTS = "tts"
SPAN_VOICE_STT = "stt"
SPAN_VOICE_EOU = "eou_detection"
SPAN_VOICE_AMD = "amd"

# GenAI Operations (OTel SemConv v1.41.0)
SPAN_GEN_AI_CHAT            = "chat"
SPAN_GEN_AI_EXECUTE_TOOL    = "execute_tool"
SPAN_GEN_AI_INVOKE_AGENT    = "invoke_agent"
SPAN_GEN_AI_INVOKE_WORKFLOW = "invoke_workflow"
```

### Key Attributes

| Constant | Attribute String | Description |
|----------|------------------|-------------|
| `ATTR_SESSION_ID` | `session.id` | Unique UUID v7 session identifier. |
| `ATTR_SESSION_CONVERSATION_ID` | `session.conversation_id` | Conversation grouping identifier. |
| `ATTR_SESSION_MODALITY` | `session.modality` | Interaction modality (`"voice"`, `"text"`, `"multimodal"`). |
| `ATTR_SESSION_AGENT_ID` | `session.agent_id` | Canonical deployment ID. |
| `ATTR_GEN_AI_AGENT_VERSION` | `gen_ai.agent.version` | Agent version string. |
| `ATTR_SESSION_METADATA_PREFIX` | `session.metadata.` | Prefix for custom user metadata keys. |
| `ATTR_PLATFORM_REF_PREFIX` | `platform.ref.` | Prefix for external reference keys. |
| `ATTR_GEN_AI_MODEL` | `gen_ai.request.model` | Model name. |
| `ATTR_GEN_AI_IN_TOKENS` | `gen_ai.usage.input_tokens` | Prompt/input tokens. |
| `ATTR_GEN_AI_OUT_TOKENS` | `gen_ai.usage.output_tokens` | Completion/output tokens. |
| `ATTR_GEN_AI_COST_USD` | `gen_ai.usage.cost_usd` | Incurred LLM cost in USD. |
