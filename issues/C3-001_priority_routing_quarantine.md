TL;DR
- Introduce priority routing for control messages (Cancel/Interrupt) over bulk traffic (Output/Display/Progress) and quarantine slow interceptors after repeated budget violations.

Background / Problem
- Under bursty traffic, cancellations must remain prompt and interceptors that exceed budgets should not degrade the system.

Scope (In) / Non‑Goals (Out)
- In: two-tier priority queues; semaphore per class; interceptor timing and demotion to a low-priority pool.
- Out: per-message dynamic priorities beyond control vs data.

Design Direction
- Assign control messages to a high-priority path; data messages to normal path; keep per-class concurrency limits.
- Track interceptor runtimes; after N budget violations, execute in a quarantined low-priority lane.

Config
- CAPS_ROUTING_PRIORITY_WEIGHTS
- CAPS_INTERCEPTOR_BUDGET_MS (default: 10)
- CAPS_INTERCEPTOR_VIOLATIONS_N (default: 3)

Observability
- Metrics: cancel_latency_ms (P95 target), interceptor_quarantine_total
- Logs: warnings on budget overrun and demotion

Test Plan
- Adversarial floods: cancel remains prompt (P95 < 50ms); quarantine applied; no deadlocks; ordering remains consistent.

Acceptance Criteria
- Prompt cancel under load; quarantining works; tests pass.

Implementation Notes (repo‑specific)
- Extend src/session/manager.py routing paths and interceptors accounting; consider minimal changes to framing for control tagging if needed.

Open Questions
- Should we expose per-interceptor metrics breakdown in Session.info()?

