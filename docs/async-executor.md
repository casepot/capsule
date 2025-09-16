# Async Executor

> Status: Authoritative reference for Capsule's async execution path (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if your checkout has drifted, verify the cited files before relying on this guide).

## Purpose
- `AsyncExecutor` provides a native asyncio execution path that honors Capsule’s merge-only namespace, pump-only output, and single-reader invariants while the worker still defaults to `ThreadedExecutor` for compatibility (`src/subprocess/async_executor.py:186`, `docs/architecture-overview.md:8`).
- It is currently instantiated through the integration stack (Resonate bridge and durable functions) rather than the worker loop, enabling feature-gated adoption and experimentation alongside the legacy threaded model (`src/integration/resonate_wrapper.py:43`, `docs/architecture-overview.md:55`).
- Use this document when implementing async-capable capabilities, tuning detection heuristics, or preparing the worker routing change tracked in EW-010 (#51).

## Mode Analysis & Routing
- `ExecutionMode` encodes the five routing outcomes: `TOP_LEVEL_AWAIT`, `ASYNC_DEF`, `BLOCKING_SYNC`, `SIMPLE_SYNC`, and `UNKNOWN` (`src/subprocess/async_executor.py:68`).
- `analyze_execution_mode` parses the code, checks for top-level await, async definitions, and blocking heuristics, then defaults to simple sync; a fast-path treats any source containing `await` as TLA to avoid redundant parsing (`src/subprocess/async_executor.py:405`, `src/subprocess/async_executor.py:805`).
- Blocking detection walks the AST twice to capture imports and call sites, maintains alias maps, and applies configurable guards: module-scope overshadow guard, import requirement for attribute calls, and per-module method allowlists (`src/subprocess/async_executor.py:520`). Telemetry counters (`detected_blocking_import`, `detected_blocking_call`, `missed_attribute_chain`, `overshadow_guard_skips`) increment as the detector runs (`src/subprocess/async_executor.py:579`).
- Limitations today: overshadowing is module-scope only, attribute provenance is shallow, and nodes missing `lineno` skip ordering checks (`src/subprocess/async_executor.py:535`). Fold tighter heuristics into this guide once they ship so downstream callers do not need to read code to learn the edge cases.

## Execution Flow
### Simple synchronous code
- `_execute_simple_sync` distinguishes expressions via `ast.parse(..., mode='eval')`, compiles with `<session>`, evaluates against the live namespace, merges locals first, then applies a filtered globals diff, recording the expression result (`src/subprocess/async_executor.py:918`). Result history and merge-only behavior leverage `NamespaceManager.update_namespace` and `_compute_global_diff` (`src/subprocess/namespace.py:68`, `src/subprocess/async_executor.py:1417`).
- Unit coverage asserts expression results and namespace updates behave as expected (`tests/unit/test_async_executor_helpers.py:132`).

### Async definitions (no top-level await)
- `_execute_async_definitions` always compiles in exec mode, merges locals/globals identically to the sync path, and returns `None` (`src/subprocess/async_executor.py:985`). This preserves namespace updates for later awaited calls without registering new coroutines.

### Top-level await
- `_execute_top_level_await` compiles with `PyCF_ALLOW_TOP_LEVEL_AWAIT`, preferring the eval path to preserve expression values, falling back to exec if eval raises `SyntaxError` (`src/subprocess/async_executor.py:1016`).
- When compilation produces coroutine code, the executor tracks it, awaits with `asyncio.timeout`, annotates cancellations/timeouts, and records expression results. Locals from eval/exec branches merge before applying global diffs, and the namespace is pre-seeded with `asyncio` for reuse (`src/subprocess/async_executor.py:1056`, `src/subprocess/async_executor.py:1073`).
- Tests demonstrate both expression-returning awaits and assignment scenarios, validating result history updates (`tests/unit/test_top_level_await.py:20`).

### AST fallback wrapper
- If both flagged compiles fail, `_execute_with_ast_transform` parses the source into a wrapper function with a unique virtual filename, optionally applies gated transforms (def→async def rewrite and async-lambda helper), registers the code in `linecache`, and awaits the wrapper under a timeout (`src/subprocess/async_executor.py:1189`).
- Wrapper execution merges locals (filtered to exclude internals), applies the same global diff filter, records expression results when applicable, and warns if the wrapper returns a non-dict for statement bodies (`src/subprocess/async_executor.py:1338`).
- Stats capture how many transforms were applied (`ast_transform_def_rewrites`, `ast_transform_lambda_helpers`), and dedicated tests cover both transforms and fallback namespace merges (`tests/unit/test_async_executor_helpers.py:43`).

### Blocking sync delegation
- `_execute_with_threaded_executor` constructs a `ThreadedExecutor`, reuses the worker’s output pump, and awaits the threaded async wrapper to keep pump ordering and namespace behavior consistent for blocking or `input()`-driven code (`src/subprocess/async_executor.py:857`). The method requires a running event loop and transport, mirroring event-loop ownership rules (`src/subprocess/executor.py:239`).
- The delegated path inherits the threaded executor’s drain policy, including current timeout suppression defaults (see EW-011/#48).

## Namespace & Result Management
- Namespace merges rely on `NamespaceManager.update_namespace` to maintain merge-only semantics and protected keys (`src/subprocess/namespace.py:68`). `_compute_global_diff` filters builtins, engine internals, and dunder names while comparing by identity to detect new bindings (`src/subprocess/async_executor.py:1417`).
- Expression results funnel through `NamespaceManager.record_expression_result` to maintain IPython-style `_`, `__`, `___` history (`src/subprocess/namespace.py:116`).
- AST fallback locals merge excludes `__async_exec__`, `asyncio`, and dunder names, preventing leakage of wrapper internals (`src/subprocess/async_executor.py:1391`).

## Cancellation Semantics
- `_CoroutineManager` tracks the single top-level coroutine, records cancel metadata, and schedules `task.cancel()` either directly on the loop or through `call_soon_threadsafe` (`src/subprocess/async_executor.py:75`).
- `cancel_current()` increments telemetry counters (`cancels_requested`, `cancels_effective`, `cancels_noop`), logs the outcome, and delegates to `_CoroutineManager.cancel` (`src/subprocess/async_executor.py:1635`). Cancellation notes include mode, reason, and timestamp for observability (`src/subprocess/async_executor.py:1457`).
- Current implementation lacks the pending-cancel handshake described in EW-013 (#46); cancellation issued before `set_top()` completes is treated as a no-op. Tests cover prompt cancellation, AST fallback, idempotence, and background task preservation (`tests/unit/test_async_executor_cancellation.py:16`).

## Configuration & Environment Knobs
- Constructor parameters expose detection policy overrides, AST cache sizing, TLA timeout, and fallback linecache capacity (`src/subprocess/async_executor.py:223`). When left at defaults, environment variables supply overrides: `ASYNC_EXECUTOR_AST_CACHE_SIZE`, `ASYNC_EXECUTOR_ENABLE_DEF_AWAIT_REWRITE`, `ASYNC_EXECUTOR_ENABLE_ASYNC_LAMBDA_HELPER`, and `ASYNC_EXECUTOR_FALLBACK_LINECACHE_MAX` (`src/subprocess/async_executor.py:300`).
- Detection policy fields (`blocking_modules`, `blocking_methods_by_module`, `warn_on_blocking`, `enable_overshadow_guard`, `require_import_for_module_calls`) can be customized per instance and propagate into stats/logging (`src/subprocess/async_executor.py:381`).
- Stats include execution counts, per-mode tallies, detection counters, cancellation telemetry, coroutine cleanup counts, and AST transform counters (`src/subprocess/async_executor.py:320`). These metrics support external diagnostics once surfaced by EW-012 (#49).

## Observability & Testing
- Structured logging records initialization, execution start, AST fallback, cancellations, and cleanup events (`src/subprocess/async_executor.py:398`, `src/subprocess/async_executor.py:824`).
- Unit suites cover TLA behavior, AST helpers, cancellation, namespace binding, timeout annotation, and loop ownership (`tests/unit/test_top_level_await.py:16`, `tests/unit/test_async_executor_helpers.py:25`, `tests/unit/test_async_executor_cancellation.py:16`, `tests/unit/test_async_executor_namespace_binding.py:62`, `tests/unit/test_async_executor_timeout.py:16`, `tests/unit/test_event_loop_handling.py:17`). Treat these as authoritative examples when documenting behavior or writing new tests.

## Integration Notes
- `async_executor_factory` wires instances for DI, deriving defaults from `ctx.config`, and ensures environment knobs remain opt-in; it also reiterates the loop-ownership constraint (no new loops in durable layers) (`src/integration/resonate_wrapper.py:43`).
- `register_executor_functions` registers the `durable_execute` generator, proving the promise-first integration path where AsyncExecutor runs behind the protocol bridge without touching the transport directly (`src/integration/resonate_functions.py:20`).
- Worker routing is not yet enabled; EW-010 (#51) will gate direct usage behind `WORKER_ENABLE_NATIVE_ASYNC` while respecting pump ordering and cancellation invariants (`docs/architecture-overview.md:55`). Until then, AsyncExecutor usage is confined to integration contexts, tests, and manual tooling.

## Known Limitations & Planned Work
- Pending cancel handshake: `_CoroutineManager` drops cancels issued before task registration; EW-013 (#46) tracks fixing this race and the related telemetry expectations.
- Drain timeout suppression: delegation to `ThreadedExecutor.execute_code_async()` still suppresses drain timeouts by default; EW-011 (#48) will add a configurable policy.
- Code object caching: only ASTs are cached today; EW-014 (#47) will introduce a bounded code-object LRU to reduce compile overhead.
- Config plumbing: session-level overrides for pump and timeout policy remain hard-coded in the worker; EW-012 (#49) will plumb these values to both executors.
- Worker integration: routing async modes inside the worker process depends on EW-010 (#51) and will require careful validation of output-before-result semantics.
- Blocking detection heuristics intentionally skip provenance tracking and consume module-scope bindings only. Expand this section or add a dedicated “Heuristics” appendix when provenance tracking work is scheduled so limitations and counters stay easy to audit.

## Documentation Notes
- The implementation preserves the compile-first and merge-only invariants documented in `docs/architecture-overview.md`; expand this guide with additional rationale if future contributors need more historical background than the architecture summary provides.
- Phase 3 “Future” items (order-aware binding, provenance tracking, strict-mode options) remain outstanding enhancements. Keep the “Known Limitations & Planned Work” list above in sync or file new roadmap entries so expectations for AsyncExecutor stay centralized.
