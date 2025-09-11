TL;DR
- Complete bridge lifecycle and observability: expose pending counts, high‑water mark, timeouts_total, canceled_total; surface via Session.info(). Ensure idempotent close/cancel_all.

Background / Problem
- A local-mode ResonateProtocolBridge exists (src/integration/resonate_bridge.py) and tracks pending and a high-water mark. We need a first-class, tested metrics surface and lifecycle semantics.

Scope (In) / Non‑Goals (Out)
- In: metrics getters; wire into Session.info(); idempotent close()/cancel_all(); tests covering teardown and races.
- Out: new protocol messages; major API changes.

Design Direction
- Keep bridge small; add counters and expose them; ensure no pending remain after close; repeated open/close is safe.

Observability
- Expose pending_high_water_mark(), current_pending(), timeouts_total, canceled_total; Session.info() includes bridge metrics (and pool state if available).

Test Plan
- No pending after close(); repeat open/close idempotent; concurrent cancel safety; metrics reflect expected values.

Acceptance Criteria
- Session.info() surfaces bridge metrics; lifecycle correctness tests pass.

Implementation Notes (repo‑specific)
- Extend src/integration/resonate_bridge.py with metrics + lifecycle helpers and integrate with manager interceptors.

Open Questions
- Should metrics also emit via structlog with a standard key pattern for dashboards?

