TL;DR
- Finalize and harden the SessionPool with warm imports, memory budget guard rails, and clearer metrics/operations. The pool already exists (event-driven warmup and health checks); this issue focuses on polish and production readiness.

Background / Problem
- Cold start latency is expensive. We have an event-driven pool (src/session/pool.py) with warmup and health checks; we should add pre-import hooks for common modules and enforce memory budget/TTL policies.

Scope (In) / Non‑Goals (Out)
- In: warm imports per session during warmup; memory budget (evict/recycle); metrics surfaced via get_info(); docs and CI defaults.
- Out: multi-tenant fairness and admission control (future work).

Design Direction
- Warm imports: execute configured imports per new session after ready; failures should not poison the pool (log and continue/evict).
- Memory budget: periodically sample RSS of idle sessions and evict over budget; log events and update metrics.
- Keep event-driven warmup and hybrid health check model.

API / Config
- New: CAPS_POOL_WARM_IMPORTS: list[str]
- New: CAPS_POOL_MEM_BUDGET_MB: int (budget across pool)
- Keep: min_idle, max_sessions, session_timeout, recycle_after_executions.

Observability
- Metrics: pool_hit_rate, warmup_seconds, idle_count, evictions_total, mem_mb; expose via pool.get_info().

Security
- No change to capability policy; warm imports are configured by operator.

Compatibility
- Opt-in configuration; no protocol changes.

Performance Targets
- P50 acquisition from pool hit < 100ms; warm import per worker < 3s for common stacks.

Test Plan
- Unit: warm import success/failure behavior (does not deadlock); TTL reaping; mem budget enforcement evicts cleanly.
- Load: churn tests sustain responsiveness; stop() leaves no dangling sessions.

Rollout
- Default size 0 in CI; 2 in dev; document per-env overrides.

Dependencies
- None hard; leverages existing Session.

Risks & Mitigations
- Memory bloat: budget guard rails + recycle strategy; health checks.

Acceptance Criteria
- Warm imports and mem budget are configurable and visible via metrics; pool remains healthy under churn; tests pass.

Implementation Notes (repo‑specific)
- Extend src/session/pool.py warmup flow to run imports; sample psutil RSS per session where available.
- Update docs to reflect new knobs and expected behavior.

Open Questions
- Preload caps.* stubs during warmup (cheap)?

