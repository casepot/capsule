TL;DR
- Add a distributed execution trace: an append-only timeline of key events per execution_id across session, worker, bridge, and providers. Provide a retrieval API and redaction policy.

Background / Problem
- Operators and developers need to answer “what happened and why” without reproducing failures. A structured trace enables this.

Scope (In) / Non‑Goals (Out)
- In: trace event model; in-memory store (ring buffer) per session; basic emit hooks; retrieval API; redaction controls.
- Out: external storage/export (future hook).

Design Direction
- Keep TraceEvent minimal and strict to avoid drift; redact payloads by policy; correlate with message ids and correlation ids.

Types (proposed)
```py
class TraceEvent(BaseModel):
    ts: float
    execution_id: str
    kind: str                 # e.g., "execute.accepted", "capability.request", "provider.response"
    correlation_id: str
    attrs: dict[str, object]  # redacted as needed
```

API
- trace = await caps.diagnostics.get_trace(execution_id="run-123")

Observability
- Optional export hook (callback) for external systems; keep default in-memory, bounded.

Test Plan
- Multi-capability run with cancel; verify event ordering and correlation; redaction enforced.

Acceptance Criteria
- Trace reconstructs lifecycle deterministically for typical runs; tests pass.

Implementation Notes (repo‑specific)
- New module: src/diagnostics/trace.py; add emit points in src/session/manager.py, src/subprocess/worker.py (key transitions), src/integration/resonate_bridge.py, and providers.
- Expose via B1 as caps.diagnostics.get_trace.

Open Questions
- What retention window/size do we want per session by default?

