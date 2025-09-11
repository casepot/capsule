TL;DR
- Add durable streaming channels with open/data/close semantics and backpressure. Expose as async generators in user space once providers exist.

Background / Problem
- Single request/response isn’t sufficient for GUI/log/event feeds. We need ordered, durable streams with clear lifecycle and cancel integration.

Scope (In) / Non‑Goals (Out)
- In: StreamOpen/Data/Close messages; window/backpressure in router; cancel integration; metrics.
- Out: GUI provider itself (later).

Design Direction
- Exactly-once delivery within a session; per-stream ordered by seq.
- Implement a bounded window (or queue) to apply backpressure; optionally add credit messages in a future iteration.
- Cancellation interoperates with Session.cancel/interrupt.

Types / Schemas (proposed)
```py
class StreamOpenMessage(BaseModel):
    type: Literal["stream_open"] = "stream_open"
    id: str
    timestamp: float
    stream_id: str
    capability: str
    params: dict

class StreamDataMessage(BaseModel):
    type: Literal["stream_data"] = "stream_data"
    id: str
    timestamp: float
    stream_id: str
    chunk: bytes | str
    seq: int
    more: bool = False

class StreamCloseMessage(BaseModel):
    type: Literal["stream_close"] = "stream_close"
    id: str
    timestamp: float
    stream_id: str
    reason: Literal["end", "error", "cancel", "policy"]
    error: str | None = None
```

Public APIs
- async for evt in caps.<domain>.<stream>(…): yield decoded events/chunks.

Invariants
- Ordered per stream by seq; close is final; post-close data is discarded (metric incremented).

Error Semantics
- Provider crash → stream_close(reason="error"); cancel → reason="cancel".

Config
- CAPS_STREAM_WINDOW_SIZE (default: 64)
- CAPS_STREAM_QUEUE_MAX (default: 1024)

Observability
- Metrics: streams_open_total, stream_backlog_hwm, stream_dropped_total
- Traces: stream.open/data/close events

Security
- Streams are gated by policy like regular capabilities.

Compatibility
- Additive protocol.

Performance Targets
- Sustain ≥ 50k msgs/min across ~100 streams on dev hardware.

Test Plan
- Lifecycle (open→data*→close), cancel integration, provider disconnect mid-stream, ordering and backpressure behavior.

Rollout
- Behind CAPS_ENABLE_STREAMS for initial validation.

Dependencies
- B1 (registry/policy) for user space wrappers/generation.

Risks & Mitigations
- Misconfigured backpressure → bounded queues and clear limits.

Acceptance Criteria
- async generator UX works end-to-end with a mock stream; metrics and ordering validated.

Implementation Notes (repo‑specific)
- Files: src/protocol/messages.py (add message types), src/protocol/framing.py (extend StreamMultiplexer or add credit), src/session/manager.py (stream registry, windowing, cancel), src/integration/resonate_bridge.py (optional correlation hooks).

Open Questions
- Favor bytes vs UTF-8 text for event payloads by default?

