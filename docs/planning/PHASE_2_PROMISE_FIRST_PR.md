# Phase 2: Promise‑First Integration & Integration Stabilization (Delivered)

This PR delivers Phase 2 of the Capsule transition: Promise‑First refinement (2b) and Integration Stabilization (2c) in local mode, along with documentation and test hygiene updates aligned with the single‑loop invariant.

## Summary
- Promise‑first durable execution with `ctx.promise` + Protocol Bridge.
- Complete protocol correlation for Execute → Result/Error and Input → InputResponse.
- Enforce single event‑loop ownership (session/transport); no loop creation in durable functions.
- Stabilize integration: output ordering (outputs before result), large output chunking, checkpoint create/restore, and concurrent safety.

## Motivation & References
- FOUNDATION_FIX_PLAN.md (Phase 2b/2c scope, goals, and current status)
- 00_foundation_resonate.md (Promise‑first durable pattern)
- 21_spec_resonate_integration.md (Promises, DI, durable registration)
- 22_spec_async_execution.md (single-loop invariant, mode routing)
- 24_spec_namespace_management.md (merge‑only namespace; ENGINE_INTERNALS)
- 25_spec_api_reference.md (public API expectations)
- 20_spec_architecture.md (layering: execution, capabilities, transport)

## Scope (In/Out)
- In (delivered): Durable promise‑first wiring; ResonateProtocolBridge execute/result/error correlation; centralized promise‑ID constants; session message interceptors; worker drain‑policy enforcement; checkpoint/restore handlers (local slice); tests; small doc polish.
- Out: Native async executor path (Phase 3); remote Resonate mode (Phase 5); extended capability system (Phase 4); perf gates.

## Final Outcomes (Acceptance Criteria)
- Durable functions never create/manage event loops; use `ctx.promise` + bridge exclusively.
- Bridge resolves/rejects promises deterministically: Execute via Result/Error; Input via InputResponse.
- Promise IDs centralized: `exec:{execution_id}`; inputs `exec:{execution_id}:input:{input_id}`.
- Session manager is the sole transport reader; bridge observes via interceptors.
- Worker drains outputs before Result; on drain timeout, emits a single `ErrorMessage` (OutputDrainTimeout) and withholds Result to preserve ordering; `execution_time` always set.
- Checkpoint/restore (local slice): bytes round‑trip; restore merges namespace without replacing; ENGINE_INTERNALS preserved.
- Busy guard: concurrent execute rejected with `Busy` error and no cross‑talk.
- Added test observer helper and migrated/marked tests to avoid competing readers.

## Design Overview
1) Durable Functions (src/integration/resonate_functions.py)
- Replace `ctx.lfc` with promise‑first:
  - `promise = yield ctx.promise(id=f"exec:{execution_id}")`
  - `yield bridge.send_request("execute", execution_id, ExecuteMessage(...), timeout=ctx.config.tla_timeout)`
  - `result = yield promise`
- Keep pre/post checkpoints; no asyncio APIs here.

2) Protocol Bridge (src/integration/resonate_bridge.py)
- Centralized ID formats via `src/integration/constants.py`.
- Correlate Execute by execution_id; correlate Input by input_id.
- Cleanup `_pending` on resolve/reject; robust JSON handling.
- Local breadcrumb for `_pending` high‑water mark with TODO(Phase 3) to expose a metric.

3) Session Manager Interceptors (src/session/manager.py)
- Add `add_message_interceptor(callable)` / `remove_message_interceptor(callable)`.
- Invoke interceptors in the `_receive_loop` only (before routing) to avoid duplicate invocation; they do not consume messages.
- Register bridge `route_response` as an interceptor via DI init (see resonate_init).

4) Worker Stabilization (src/subprocess/worker.py)
- Enforce output‑before‑result using `drain_outputs` barrier.
- On drain timeout → emit ErrorMessage with `OutputDrainTimeout`; result is withheld to preserve ordering (documented warning log and spec note); always set `execution_time`.
- Minimal checkpoint/restore (local slice) using CheckpointManager; default merge‑only restore preserving ENGINE_INTERNALS with `clear_existing=False`; full replacement when `clear_existing=True`.

5) Capability Input (src/integration/capability_input.py)
- Continue using promise‑based bridge; unify promise id format; ensure invalid JSON handling returns safe defaults.

## File‑Level Change Summary (Implemented)
- src/integration/constants.py: new constants + helper functions for promise IDs.
- src/integration/resonate_bridge.py: deterministic correlation + timeout enrichment + `_pending` HWM breadcrumb.
- src/session/manager.py: interceptors (already present) validated via tests.
- src/subprocess/worker.py: drain‑policy warning + stable OutputDrainTimeout error shape.
- src/subprocess/executor.py: async wrapper emits a one‑time warning when drain timeout is suppressed in tests.
- tests: new unit tests for drain‑timeout error shape and interceptor exception handling; observer utility to await messages in tests.

## Test Plan (Executed)
- Unit
  - ResonateProtocolBridge: execute/result/error correlation; pending cleanup; invalid JSON safety.
  - Session manager: interceptors invoke and do not break routing; exceptions in interceptors don’t break routing.
  - Worker: drain‑timeout error shape with stable exception type/message.
  - Checkpoint bytes/invalids (existing coverage retained).
- Integration (local)
  - Durable execute resolution; output messages precede result (long/CR outputs); Busy guard; checkpoint round‑trip.
- E2E/Features (if applicable)
  - HITL input round‑trip (Phase 3 enhancements tracked).

## Risks & Mitigations
- Event loop conflicts: Only session reads transport; bridge is interceptor callback. No durable loop creation.
- Message ordering regressions: Maintain `drain_outputs` pre‑result; worker emits OutputDrainTimeout error and withholds result on timeout.
- Namespace integrity on restore: Never replace namespace dict; merge updates; preserve ENGINE_INTERNALS.
- Promise leaks: Ensure `_pending` cleanup on resolve/reject; add unit assertions.

## Performance & Telemetry
- Preserve current chunk sizes and frame limits; no extra copies.
- Structured logs include session/loop ids for invariant checks.
- Optional metrics: `_pending` HWM breadcrumb in bridge; further metrics deferred to Phase 3 to avoid runtime cost.

## Rollout & Backout
- Rollout: land interceptors + bridge correlation + durable promise‑first behind local mode only.
- Backout: revert durable function to `ctx.lfc` wrapper and disable interceptors (docs only; no code changes here).

## Tasks & Checklists
- Durable functions
  - [x] Promise‑first design and id conventions documented (Phase 3: native path)
- Bridge
  - [x] Execute/Result/Error correlation by execution_id
  - [x] Input/InputResponse correlation by input_id
  - [x] Pending cleanup on resolve/reject; `_pending` HWM breadcrumb
- Session Manager
  - [x] Interceptor API validated; ordering of interceptor then routing
- Worker
  - [x] Output drain before result enforced; OutputDrainTimeout error shape
  - [x] execution_time set
- Capability
  - [x] Promise id conventions; payload handling
- Tests
  - [x] Unit and integration coverage per Test Plan
  - [x] Observer helper to await Ready/Checkpoint via interceptor


## Non‑Goals
- Native AsyncExecutor (Phase 3), remote mode (Phase 5), full capability system (Phase 4).

---

Maintainers: please review scope, acceptance criteria, and the file‑level change plan before implementation. This document will guide the subsequent implementation PRs.
