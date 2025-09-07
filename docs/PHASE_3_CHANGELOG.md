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
