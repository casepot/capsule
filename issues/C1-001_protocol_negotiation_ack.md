TL;DR
- Add HelloMessage(protocol_version) on session open for version checks and AckMessage(ack_of, accepted_ts) to acknowledge accepted requests immediately upon enqueue.

Background / Problem
- As protocol features expand, we need explicit version negotiation and fast acceptance signals to support retries and clearer UX.

Scope (In) / Non‑Goals (Out)
- In: new Hello/Ack message types; handshake at session startup; ack for execute/capability requests.
- Out: global version registry or network bootstrapping; just implement the local worker/session handshake paths.

Design Direction
- Worker and Session exchange HelloMessage; on incompatibility, return structured ErrorMessage(reason="incompatible_protocol").
- On receiving execute/capability request, enqueue then immediately emit AckMessage with correlation id.

Types / Schemas (proposed)
```py
class HelloMessage(BaseModel):
    type: Literal["hello"] = "hello"
    id: str
    timestamp: float
    protocol_version: str

class AckMessage(BaseModel):
    type: Literal["ack"] = "ack"
    id: str
    timestamp: float
    protocol_version: str
    ack_of: str  # request id
    accepted_ts: float
```

Invariants
- Ack is additive; final Result/Error still follows and closes the request’s lifecycle.

Config
- Negotiation strategy: compatible versions table; protocol minor bump as needed.

Test Plan
- Version mismatch error; ack observed within target latency; lost ack retry scenarios handled idempotently at the client.

Performance Targets
- P50 ack latency < 50ms after enqueue on dev hardware.

Acceptance Criteria
- Hello/Ack added; handshake works; ack emitted for execute/capability requests; tests pass.

Implementation Notes (repo‑specific)
- Files: src/protocol/messages.py (add types), src/session/manager.py and src/subprocess/worker.py (hello exchange; ack emission on enqueue), src/protocol/transport.py unchanged except minor type handling.

Open Questions
- What minimum protocol version do we want to advertise initially?

