# Phase 3 Changelog

This document tracks accepted work during Phase 3. Each entry summarizes behavior changes, tests, and
notable decisions. Update this file after each Phase 3 PR is validated and accepted.

## PR 1 — AsyncExecutor: Native TLA Core (compile-first)

- Implemented compile-first Top-Level Await (TLA) in `AsyncExecutor`:
  - Eval-first with `PyCF_ALLOW_TOP_LEVEL_AWAIT` to preserve expression results.
  - Exec+flags fallback for statements/mixed content.
  - AST fallback invoked only if both eval and exec compilation with TLA flags raise `SyntaxError`.
- Namespace semantics preserved:
  - Execute against the live namespace mapping (`NamespaceManager.namespace`).
  - Merge locals first, then global diffs via `_compute_global_diff`.
  - Never replace the mapping. `ENGINE_INTERNALS` preserved via `NamespaceManager.update_namespace`.
- Result history:
  - Expression results recorded through `NamespaceManager.record_expression_result` (updates `_`, `__`, `___`).
  - Statement blocks return `None` (no attempt to evaluate trailing expression in TLA path for this PR).
- Error handling:
  - Await top-level coroutine under `asyncio.timeout(self.tla_timeout)`.
  - On timeout, annotate exceptions with timeout duration, execution id, and code snippet.
  - On dual `SyntaxError` compilation failure, add notes before falling back to AST transform.
- Observability and maintainability refinements:
  - Added `_annotate_timeout(e, code)` helper to DRY timeout notes.
  - Logged `ENGINE_INTERNALS` import failures (diff and helper path) at debug level; behavior unchanged.
  - Reordered globals snapshot to occur after ensuring `asyncio` is present to avoid spurious diffs.
  - TLA analysis detects top-level `async for` and `async with` constructs.
- Tests updated/added:
  - Compile-first path assertions for assignment, multiple awaits, comprehensions.
  - f-string with `await` (Python >= 3.12) with skip on older.
  - Top-level `async for` and `async with` code paths.
  - AST fallback test forces both eval+exec compile failures under TLA flags.
  - Namespace binding tests acknowledge closure behavior is deferred to PR 3 (no AST hoisting in PR 1).
- Types/tooling:
  - mypy clean; basedpyright strict with expected Unknown warnings per `docs/TYPING.md`.
  - Addressed minor typing nits (`Task[object]` callback annotation; removed unused imports/ignores).
- Out of scope (tracked for later PRs):
  - AST transform policy (def→async and lambda helper) configurable and default-off (PR 3).
  - Coroutine lifecycle and cancellation manager (PR 4).
  - “Last expression of statement blocks” capture in TLA path (not changed in PR 1).

Merge: PR #13 (`feat/phase3-pr1-async-tla-compile-first`) merged into `master`.

## PR 2 — AsyncExecutor: Native Simple Sync + Async Def

- Native execution for simple sync and async-def defining code in `AsyncExecutor`:
  - Added `_execute_simple_sync` for expressions and statement blocks compiled with `mode='eval'`/`'exec'`.
  - Added `_execute_async_definitions` for blocks that define `async def` without awaiting.
  - Routing updated: `SIMPLE_SYNC` → native, `ASYNC_DEF` → native, `BLOCKING_SYNC` → ThreadedExecutor, `TOP_LEVEL_AWAIT` unchanged.
- Namespace semantics preserved (merge-only, identity stable):
  - Bind to live mapping (`NamespaceManager.namespace`); merge locals first, then global diffs via `_compute_global_diff`.
  - Never replace mapping; `ENGINE_INTERNALS` preserved via `NamespaceManager.update_namespace`.
  - Expression results recorded via `record_expression_result`.
- Delegation policy:
  - Delegation remains only for detected blocking sync paths (no change to detection logic).
- Tests updated/added:
  - Removed assertions that simple sync delegates to `ThreadedExecutor`.
  - Added native simple expression/statements tests; async-def defining code test ensures `__globals__` binds to live mapping and no delegation occurs.
  - Mixed sequence test (sync → async → sync) validates correct results and stable namespace identity.
  - Error propagation test on native path increments error stats.
  - Positive BLOCKING_SYNC delegation test ensures ThreadedExecutor is invoked only for blocking sync.
  - Global-diff skip-list behavior validated under AST fallback (no updates for `__async_exec__`, `asyncio`, `__builtins__`).
  - UNKNOWN/SyntaxError surfaces naturally via native path and increments error counters.
  - Coverage improved for AsyncExecutor unit scope (≈88%) by targeting routing branches and diff paths.

## PR 3 — AsyncExecutor: AST Fallback Wrapper (Minimal, PEP 657-aligned)

- Scope and behavior changes:
  - Default policy is minimal wrapper only. Broad transforms are disabled by default:
    - def→async def when body contains await: gated by `enable_def_await_rewrite=False`.
    - zero-arg lambda → async helper: gated by `enable_async_lambda_helper=False`.
  - Removed global hoisting in fallback. User statements are not reordered. For statement blocks, the wrapper appends a single `return locals()` and merges back into the live namespace (locals-first, then global diffs). `ENGINE_INTERNALS` preserved; `__async_exec__`, `asyncio`, and `__builtins__` are skipped.
- PEP 657 location mapping:
  - Parse with a stable filename `<async_fallback>` and register original source via `linecache.cache` for readable tracebacks.
  - Use `ast.copy_location` for inserted `Return` nodes; copy end positions when present.
  - Call `ast.fix_missing_locations` before compile.
- Telemetry and configuration:
  - Added counters: `stats["ast_transforms"]`, `stats["ast_transform_def_rewrites"]`, `stats["ast_transform_lambda_helpers"]`.
  - `AsyncExecutor.__init__` now accepts flags; `async_executor_factory` threads `ctx.config.enable_def_await_rewrite` and `ctx.config.enable_async_lambda_helper` (default OFF). Optional env overrides are supported.
- Tests:
  - Updated fallback tests to assert minimal wrapper semantics and no reordering.
  - Added traceback mapping test asserting correct line numbers under `<async_fallback>`.
  - Adjusted invalid await placement tests: lambda/regular def with await now raise `SyntaxError` by default.
  - Namespace-binding tests updated to reflect no hoist (wrapper locals can shadow globals).

- Additional updates after review:
  - Per-execution virtual filenames for fallback:
    - Replaced single global `<async_fallback>` with unique, readable filenames: `<async_fallback:{exec_id}:{md5[:8]}:{seq}>`.
    - Prevents linecache collisions under concurrency and keeps tracebacks unambiguous.
    - Tests updated to assert filename prefix (`<async_fallback`) and line numbers; spec amended to allow unique virtual filenames.
  - Linecache lifecycle management:
    - Registered sources are now tracked per executor with a bounded LRU (default 128 entries).
    - New constructor parameter `fallback_linecache_max_size` (env: `ASYNC_EXECUTOR_FALLBACK_LINECACHE_MAX`).
    - Old entries are evicted from `linecache.cache` when over capacity; all entries cleaned on `AsyncExecutor.close()`.
    - New tests validate unique filenames, LRU eviction, and cleanup on close.
  - Correctness improvement (flagged def→async path):
    - `_contains_await` is now scope-aware and does not descend into nested scopes (FunctionDef/AsyncFunctionDef/Lambda/ClassDef).
    - Added a test ensuring an outer def is not rewritten when only an inner async def contains `await`.
  - Documentation/docstrings:
    - `AsyncExecutor.__init__` and `async_executor_factory` docstrings document the new flags, defaults (OFF), and env override behavior.
    - Async execution spec updated to permit unique fallback filenames and includes migration notes for no hoist.

- Future Work
  - Performance niceties (as needed):
    - Cache `splitlines()` result per fallback call before registering in `linecache`.
    - If def-rewrite usage expands, consider a dedicated visitor to avoid repeated traversals approaching O(n²).
  - Follow-ups (optional):
    - Log LRU evictions at debug level for observability.
    - Thread `fallback_linecache_max_size` through `async_executor_factory` from `ctx.config`.
    - Add an opt-in mode to skip `close()` cleanup for post-mortem traceback retention.
  - Semantics (discussion):
    - Unexpected non-dict return from statement wrapper: current behavior warns, skips locals merge,
      applies global diffs, and returns the value (recorded in result history). Consider normalizing
      to `None` for strict "statements return None" semantics; document trade-offs if changed.

- Migration note:
  - The fallback wrapper no longer injects a `global` hoist for simple assignments. As a result, names
    assigned within the wrapper body are locals of the wrapper and can shadow module globals. Functions
    defined in the same cell may close over those locals and not observe later global updates defined in
    subsequent cells. To regain previous behavior, prefer one of the following:
    - Add explicit `global <name>` in user code where appropriate.
    - Split code across cells so global values are assigned before function definitions (module-level defs).
    - Avoid relying on side effects within the same cell where functions are defined and used.
  - The optional AST transforms (def→async and lambda helper) do not reintroduce hoisting; they are
    independent and remain OFF by default.

## PR 4 — Coroutine Lifecycle + Cancellation Management

- Scope:
  - Introduced an internal, lightweight coroutine manager to track the AsyncExecutor's top-level coroutine and wrapping task, enabling cooperative cancellation without touching user-launched background tasks.

- Key changes:
  - Top-level coroutine/task registration: when TLA (eval/exec) yields a coroutine or when executing the AST wrapper, the executor wraps it in an `asyncio.Task`, registers it as the current top-level, and also weakref-tracks the coroutine for leak guards.
  - Added `AsyncExecutor.cancel_current(reason: str | None = None) -> bool` to cancel only the registered top-level task. Idempotent; returns False when nothing is running.
  - Cancellation and timeout notes: `CancelledError` and `TimeoutError` are annotated with `execution_id`, `mode`, optional `cancel_reason`, an optional timestamp, and the first ~160 chars of code. AST fallback timeout path annotated for parity.
  - Telemetry: added counters `cancels_requested`, `cancels_effective`, `cancels_noop`, `cancelled_errors`, and `coroutines_closed_on_cleanup`.
  - Cleanup reliability: executor always clears the top-level registration and runs `cleanup_coroutines()` in `finally`. Cleanup now discards refs post-close so subsequent calls return 0.
  - Thread-safety and responsiveness: off-loop cancellation uses `loop.call_soon_threadsafe(task.cancel)` without blocking the caller; if the loop is not running, `cancel_current()` is a no-op.

- Tests (unit):
  - TLA cancellation interrupts promptly (<100ms), raises `CancelledError` with notes, and does not increment `errors`.
  - AST fallback cancellation mirrors TLA behavior under a forced fallback.
  - No-op cancellation returns False and increments `cancels_noop` without affecting other counters.
  - Background user tasks are not cancelled by `cancel_current()`; tests create a user task first, then cancel a long-running TLA.
  - Cleanup still works on error paths; no coroutine weakrefs leak across executions.

- Success criteria met:
  - Cancelling an in-flight TLA/AST wrapper run interrupts promptly; `cleanup_coroutines()` returns 0 afterward; telemetry reflects requested/effective/no-op accurately.

## PR 5 — Blocking I/O Detection Refinements + Telemetry

- Scope:
  - Broaden blocking I/O detection while reducing false positives via overshadowing guards and an import requirement for module-based calls.
  - Keep alias and deep attribute-chain resolution; expose config toggles and structured counters.

- Key changes (src/subprocess/async_executor.py):
  - Added `enable_overshadow_guard: bool = True`:
    - Skips blocking classification when a base/alias/direct name has been rebound at module scope before the call (e.g., `requests = object(); requests.get(...)`).
    - Guard applies to direct name calls, aliased calls, and attribute chains.
  - Added `require_import_for_module_calls: bool = True`:
    - Attribute-based calls (e.g., `mod.func()`) only considered blocking if the base module or alias was imported in the code. Prevents false positives from coincidental names.
  - Telemetry: retained `detected_blocking_import`, `detected_blocking_call`, `missed_attribute_chain` and added `overshadow_guard_skips` for observability.
  - Implementation details:
    - Collect earliest top-level bindings with `_collect_top_level_bindings(tree)` to power overshadow line checks (lineno-based heuristic, module scope). When an AST node has no line number, the guard skips overshadow comparison (treated as unknown position) rather than using a sentinel.
    - Continue to resolve alias maps for `import`/`from ... import ... as ...` and resolve attribute-chain bases.
    - Import presence still marks BLOCKING_SYNC when base module is in the policy, preserving existing behavior.

- Tests (unit):
  - Added `tests/unit/test_async_executor_detection_breadth.py` covering:
    - Overshadowing skip cases that should not detect blocking (bare name matches and deep chains), and overshadow after import where import-based detection remains.
    - Positive controls: requests/socket/urllib/os/pathlib calls and deep attribute chains remain detected.
    - Telemetry counters for `detected_blocking_import`, `detected_blocking_call`, `missed_attribute_chain`; `overshadow_guard_skips` observed when applicable.
    - Config validation: default `require_import_for_module_calls=True` suppresses unimported `requests.get(...)`; overriding `blocking_methods_by_module` is respected (e.g., `os.stat`).

- Success criteria:
  - Detection continues to cover common patterns with fewer false positives, overshadowing guards are effective, config toggles work, and counters increment as expected.

Merge: PR #20 (`feat/phase3-pr5-blocking-io-detection`) merged into `master`.

Future Improvements (not in PR 5):
- Order-aware binding: Track the most-recent binding per name (including imports) and apply the overshadow guard only when the latest pre-call binding is a user binding. This would avoid cases where a later `import` rebinds the same name and should re-enable blocking classification for calls that follow the import.
- Light provenance: Consider minimal origin tracking for names assigned from blocked modules (e.g., `x = requests.Session()`), enabling detection of `x.get(...)` patterns. Any approach must weigh performance and false-positive risks carefully and should remain opt-in or guarded by policy flags.

Security considerations:
- The overshadow guard reduces false positives but is not intended to resist deliberate evasion. Malicious code can shadow names or use dynamic imports/eval to bypass static heuristics. In security‑sensitive contexts, disable the guard and rely on subprocess isolation, timeouts, and resource limits; consider future strict modes that validate `sys.modules`.
