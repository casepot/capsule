# Phase 2 Changelog

Status: Complete (unit + integration passing)

This changelog documents Phase 2 work across durable functions, the Resonate protocol bridge, session management, worker behavior, transport serialization, and test ergonomics. It reflects the code and tests currently in the repo.

## Durable Functions (Promise‑First)

- Promise‑first `durable_execute` confirmed; uses deterministic promise id `exec:{execution_id}` via `ctx.promise`.
- On `ErrorMessage`, the bridge now rejects the durable promise; `durable_execute` expects rejection and raises a structured `RuntimeError` with `add_note` context (execution id and original rejection info).
- Timeout behavior: bridge enriches timeouts with `capability`, `execution_id`, `request_id`, and `timeout` fields and rejects accordingly; durable layer surfaces context to callers.
- No asyncio usage in durable functions; they do not create or manage loops.

## Resonate Protocol Bridge

- Correlation rules implemented (local mode):
  - Execute → Result/Error: `ExecuteMessage.id` ↔ durable id `exec:{execution_id}`; response correlates on `ResultMessage.execution_id` / `ErrorMessage.execution_id`.
  - Input → InputResponse: `InputMessage.id` ↔ durable id `{execution_id}:input:{message.id}`; response correlates on `InputResponseMessage.input_id`.
- Promise lifecycle:
  - Resolve on `ResultMessage` with JSON payload.
  - Reject on `ErrorMessage` with JSON payload.
  - Clean `_pending` for all resolve/reject paths; timeout tasks also clean up.
- Timeout enrichment:
  - `send_request(..., timeout=...)` schedules a background task to reject with structured JSON when the timeout elapses, preserving `execution_id`, `capability`, and the `request_id` used for correlation.
- Tests added:
  - Bridge correlation and cleanup, error rejection, and timeout enrichment (`tests/unit/test_resonate_protocol_bridge.py`).

## Session Manager (Single Loop + Interceptors)

- Single reader invariant preserved: only `Session` reads the transport.
- Message interceptors run on the session loop and are non‑blocking; routing is scheduled via `asyncio.create_task` to keep receive loop responsive.
- Interceptors now see all messages (including `ReadyMessage` and `HeartbeatMessage`).
- Diagnostics: session start logs include `event_loop_id`.
- Test ergonomics: integration tests no longer read the transport directly; they use interceptors or awaiters.

## Worker (Local Mode Stabilization)

- Concurrency guard: exactly one in‑flight execution per worker. A second `execute` while busy yields a deterministic `ErrorMessage` with `exception_type="Busy"` and a clear message.
- Output-before-result ordering preserved; outputs are drained prior to sending `ResultMessage` (drain timeout yields an error instead of a result).
- Checkpoint/restore minimal local semantics:
  - Checkpoint sends a `CheckpointMessage` with snapshot bytes and counts; a `ReadyMessage` is also sent for simple synchronizations.
  - Restore accepts `checkpoint_id` or inline `data` and merges namespace (merge‑only semantics; engine internals preserved).
  - Message class imports fixed; bytes serialization ensured via msgpack adjustments (below).

## Transport Serialization (Msgpack)

- Msgpack serialization switched to `model_dump(mode="python")` to preserve raw `bytes` for fields like `CheckpointMessage.data`.
- JSON path continues to use `mode="json"`.

## Integration Tests & Ergonomics

- `tests/integration/test_worker_communication.py::TestCheckpointProtocol::test_checkpoint_create_and_restore` now uses interceptors to await `CheckpointMessage`/`ReadyMessage` confirmations; no direct transport reads while session loop runs.
- Tuple/list normalization in msgpack accounted for in assertions (tuples may appear as lists on the wire).

## Documentation Updates

- 22_spec_async_execution.md: clarified promise‑first approach and single‑loop policy; durable functions do not own event loops.
- 21_spec_resonate_integration.md: added correlation and rejection semantics section; deterministic promise id formats documented; timeout enrichment behavior described.

## Next Steps (Planned)

- Tests: add explicit coverage for “Busy” concurrent executes and output‑before‑result under long/CR outputs.
- Logging: extend logs with loop/session ids at interceptor invocation points for finer tracing.
- Docs: expand API reference to crisply document correlation IDs and rejection semantics across capabilities.

