TL;DR
- Add a structured ProgressMessage and a non-blocking caps.progress.update(…) shim to report progress independent of stdout. Enforce rate limits and a drop policy so progress never delays results.

Background / Problem
- Long operations need progress feedback that doesn’t interleave unpredictably with stdout. Progress should be best-effort and bounded under backpressure.

Scope (In) / Non‑Goals (Out)
- In: new message type; worker injection of a non-blocking shim; rate limit and queue/drop policy in routing; metrics.
- Out: persistence across restarts; UI rendering beyond message emission.

Design Direction
- Keep ProgressMessage simple and additive; arrival can race with stdout but must not block execution completion.
- Implement rate limit in worker and a bounded queue in Session routing with configurable drop policy (drop_oldest by default).

Types / Schemas (proposed)
```py
from typing import Literal
from pydantic import BaseModel, Field

class ProgressMessage(BaseModel):
    type: Literal["progress"] = Field(default="progress")
    id: str
    timestamp: float
    execution_id: str
    phase: Literal["start", "update", "end"] = "update"
    step: int | None = None
    total: int | None = None
    description: str | None = None
```

Public APIs (user space)
- caps.progress.update(step=i, total=N, desc="…") — best-effort enqueue; never throws on rate/drop.

Invariants
- Progress never delays Result/Error; it may be dropped under backpressure.
- Per-execution ordering by timestamp if available; tolerate minor reordering across processes.

Error Semantics
- If rate-limited or queue-full → increment drop metrics; do not raise to user code.

Config Knobs
- CAPS_PROGRESS_RATE_LIMIT_HZ (default: 5)
- CAPS_PROGRESS_QUEUE_MAX (default: 100)
- CAPS_PROGRESS_DROP_POLICY (default: drop_oldest)

Observability
- Metrics: progress_emitted_total, progress_dropped_total, progress_rate_hz
- Trace hooks (optional) for progress.update

Security
- Plain data only; no privileged operations.

Compatibility
- Additive protocol; clients can ignore progress messages.

Performance Targets
- Enqueue overhead ≤ 50µs per call in the common case.

Test Plan
- Unit: rate-limiting correctness; phase sequencing (start→update→end); drop policy behavior.
- Load: high-frequency updates (10k/s) lead to drops; Result ordering preserved.
- Cancel: updates after cancel are ignored.

Rollout
- Default ON with conservative rate limit.

Dependencies
- None hard; independent of Display.

Risks & Mitigations
- Overuse by LLM loops → rate limit + reasonable defaults.

Acceptance Criteria
- Structured progress visible; bounded behavior under pressure; tests cover rate limit and drop.

Implementation Notes (repo‑specific)
- Files: src/protocol/messages.py (add ProgressMessage), src/subprocess/worker.py (inject shim), src/session/manager.py (bounded queue/drop policy), src/session/config.py (knobs).

Open Questions
- Should we debounce updates client-side by default (e.g., 200ms)?

