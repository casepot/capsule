TL;DR
- Replace polling in FrameBuffer.get_frame with event-driven await/notify (asyncio.Condition), matching FrameReader’s design, to reduce idle CPU and maintain latency.

Background / Problem
- src/protocol/framing.py has a TODO to replace 10ms polling with proper condition-based wakeups; this is a clear perf/refactor task.

Scope (In) / Non‑Goals (Out)
- In: implement await/notify; microbench and correctness tests; CPU idle reduction validation.
- Out: message semantics changes or framing format changes.

Design Direction
- Use asyncio.Condition to guard both buffer writes and reads; mirror FrameReader patterns; preserve max frame size checks.

Performance Targets
- Reduce idle CPU by ≥80% under no-traffic while matching or improving message latency.

Test Plan
- Microbench latency; idle CPU before/after; race tests with chunked frames; ensure no missed notifications.

Acceptance Criteria
- Event-driven FrameBuffer passes tests; measurable CPU reduction; no regressions.

Implementation Notes (repo‑specific)
- File: src/protocol/framing.py (FrameBuffer class); coordinate with existing tests in features/rate_limiter and framing-related usage.

Open Questions
- Should FrameBuffer also expose a non-blocking peek/has_frame with the same invariants?

