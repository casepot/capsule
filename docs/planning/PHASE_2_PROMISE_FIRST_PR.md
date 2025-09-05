# Phase 2: Promise‑First Integration & Integration Stabilization (PR Draft)

This PR introduces Phase 2 of the Capsule transition: Promise‑First refinement (2b) and Integration Stabilization (2c). It does not implement changes yet; it documents the planned work, acceptance criteria, and validation strategy.

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
- In: Durable function rework to promise‑first; ResonateProtocolBridge execute/result/error correlation; session message interceptors; worker checkpoint/restore handlers; ordering/backpressure validation; tests.
- Out: Full native AsyncExecutor (Phase 3); remote Resonate mode (Phase 5); full capability system (Phase 4).

## Final Outcomes (Acceptance Criteria)
- Durable functions never create/manage event loops; use `ctx.promise` + bridge exclusively.
- Bridge resolves promises for Execute via Result/Error and for Input via InputResponse.
- Session manager owns the only loop/transport; bridge routes via interceptor callbacks.
- Worker drains outputs before sending Result; execution_time always set; large outputs chunked.
- Checkpoint create/restore flows with minimal fields pass Pydantic validation; namespace restored by merge, not replace.
- Concurrent executes are handled safely (serialize or reject with clear error).
- All unit and integration tests for these behaviors pass.

## Design Overview
1) Durable Functions (src/integration/resonate_functions.py)
- Replace `ctx.lfc` with promise‑first:
  - `promise = yield ctx.promise(id=f"exec:{execution_id}")`
  - `yield bridge.send_request("execute", execution_id, ExecuteMessage(...), timeout=ctx.config.tla_timeout)`
  - `result = yield promise`
- Keep pre/post checkpoints; no asyncio APIs here.

2) Protocol Bridge (src/integration/resonate_bridge.py)
- Map Execute request id to durable promise id: `f"{execution_id}:execute:{message.id}"`.
- Resolve on ResultMessage/ErrorMessage by execution_id; resolve Input by input_id.
- Cleanup pending mappings on resolve/reject; robust JSON handling.

3) Session Manager Interceptors (src/session/manager.py)
- Add `add_message_interceptor(callable)` / `remove_message_interceptor(callable)`.
- Call interceptors inside `_route_message` for Result/Error/InputResponse; they do not consume messages.
- Register bridge `route_response` as an interceptor via DI init (see resonate_init).

4) Worker Stabilization (src/subprocess/worker.py)
- Maintain output‑before‑result by waiting for `executor.drain_outputs` before Result.
- Implement minimal checkpoint/restore protocol handlers using CheckpointManager.
- Ensure last-expression result semantics and always set `execution_time`.

5) Capability Input (src/integration/capability_input.py)
- Continue using promise‑based bridge; unify promise id format; ensure invalid JSON handling returns safe defaults.

## File‑Level Change Plan (No code in this PR)
- src/integration/resonate_functions.py: swap `ctx.lfc` → promise‑first flow; timeouts from ctx.config; no asyncio.
- src/integration/resonate_bridge.py: add Execute/Result/Error correlation; pending cleanup; enrich errors.
- src/integration/resonate_init.py: register bridge as session message interceptor; ensure single loop ownership by wiring to Session manager, not raw transport.
- src/session/manager.py: add interceptor APIs and call sites; ensure ordering of interceptor then queue routing.
- src/subprocess/worker.py: add checkpoint/restore message handling; confirm existing output drain ordering; verify execution_time set.
- src/integration/capability_input.py: confirm promise id conventions; robust payload parsing.

## Test Plan
- Unit
  - ResonateProtocolBridge: execute/result/error correlation; pending cleanup; invalid JSON safety.
  - Durable functions: promise‑first generator behavior; no loop creation; timeout propagation.
  - Session manager: interceptors invoke and do not break routing.
  - Checkpoint: minimal fields pass; create/restore round‑trip validation of sizes/counts.
- Integration (local)
  - Durable execute promise resolution; output messages precede result; long output chunking; single‑loop invariant checks via logs; concurrent execute safety.
- E2E/Features (if applicable)
  - HITL input round‑trip with promise resolution.

## Risks & Mitigations
- Event loop conflicts: Only session reads transport; bridge is interceptor callback. No durable loop creation.
- Message ordering regressions: Maintain `drain_outputs` pre‑result; add tests for ordering and slow drains.
- Namespace integrity on restore: Never replace namespace dict; merge updates; preserve ENGINE_INTERNALS.
- Promise leaks: Ensure `_pending` cleanup on resolve/reject; add unit assertions.

## Performance & Telemetry
- Preserve current chunk sizes and frame limits; no extra copies.
- Structured logs include session/loop ids for invariant checks.
- Optional metrics: counts of detected blocking calls remain observational in Phase 2.

## Rollout & Backout
- Rollout: land interceptors + bridge correlation + durable promise‑first behind local mode only.
- Backout: revert durable function to `ctx.lfc` wrapper and disable interceptors (docs only; no code changes here).

## Tasks & Checklists
- Durable functions
  - [ ] Replace `ctx.lfc` with promise‑first flow.
  - [ ] Remove any asyncio usage from durable bodies.
  - [ ] Pre/post checkpoints kept.
- Bridge
  - [ ] Execute/Result/Error correlation by execution_id.
  - [ ] Input/InputResponse correlation by input_id.
  - [ ] Pending cleanup on resolve/reject; robust JSON handling.
- Session Manager
  - [ ] Add interceptor APIs and wire into `_route_message`.
  - [ ] Register bridge interceptor in local DI init.
- Worker
  - [ ] Implement checkpoint/restore protocol handlers.
  - [ ] Ensure output drain before result; execution_time set.
- Capability
  - [ ] Validate input capability promise id and payload handling.
- Tests
  - [ ] Unit and integration coverage per Test Plan.

## Non‑Goals
- Native AsyncExecutor (Phase 3), remote mode (Phase 5), full capability system (Phase 4).

---

Maintainers: please review scope, acceptance criteria, and the file‑level change plan before implementation. This document will guide the subsequent implementation PRs.

