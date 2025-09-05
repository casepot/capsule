# Phase 1 Implementation Summary

This document summarizes the Phase 1 work implementing a production‑ready AsyncExecutor with correct top‑level await (TLA) semantics, robust namespace management, intelligent execution routing, and groundwork for Resonate integration.

## Problem Statements and Solutions

- TLA expression results: Direct TLA path compiled with `exec` returns `None` for expressions. Fixed by eval‑first strategy using `PyCF_ALLOW_TOP_LEVEL_AWAIT` (0x2000) and checking `CO_COROUTINE` to await results; integrates `asyncio.timeout()` for cancellation.
- Namespace merging: Implemented locals‑first merge, then global diff application via `_compute_global_diff` to avoid replacement and ensure global writes win. Preserves engine internals.
- AST fallback: Added robust fallback with pre‑transformations (def→async def when body contains await; zero‑arg lambda with await rewritten to async def helper). Added conservative `global` hoisting for simple top‑level assignments. Applied the same snapshot/diff merge ordering as direct path.
- Execution routing: Added fast‑path routing when code contains `await`, otherwise uses AST analysis. Enhanced blocking I/O detection with alias resolution and attribute call handling (time/requests/urllib/socket/os/subprocess/pathlib/open).
- DI temporal coupling: Added `src/integration/resonate_wrapper.py` with `async_executor_factory` and `AwaitablePromise` to provide factory‑based DI without initialize() sequencing.

## Architectural Decisions

- Use Python’s `PyCF_ALLOW_TOP_LEVEL_AWAIT` value directly (0x2000).
- Detect coroutine code via `inspect.CO_COROUTINE` on compiled code objects.
- Prefer `asyncio.timeout()` (3.11+) over `wait_for` for cleaner timeouts.
- Enrich exceptions with `add_note` context where applicable.
- Merge‑only namespace policy; never replace mapping; protect `ENGINE_INTERNALS`.

## Test Coverage Improvements

- All unit tests under `tests/unit` pass locally for Python 3.12 using `uv` runner. No XPASS remain; namespace‑binding semantics validated for direct TLA and AST fallback paths.
- Added CI workflow to run unit tests on Python 3.11.
- Namespace binding, TLA correctness, AST fallback, routing, and blocking I/O analysis validated by tests.

## Known Limitations

- AST fallback performs conservative `global` hoisting for simple names; complex scoping patterns may still require further refinement.
- Blocking I/O detection aims for pragmatic coverage; may need domain‑specific extensions.
- Broader integration, capability security model, and distributed orchestration remain out of scope for this phase.

## Future Recommendations

- Add structured concurrency patterns (TaskGroup) for composed async workloads.
- Expand blocking I/O detection with configurable policies and telemetry.
- Integrate Resonate SDK end‑to‑end with durable functions and promise routing.
- Add performance micro‑benchmarks and CI perf gates for TLA latency.

## TODOs (Post‑Phase 1)

- Make TLA timeout configurable (DONE)
  - Added `tla_timeout` parameter to `AsyncExecutor` and wired via `async_executor_factory` (ctx.config supported)
  - `_execute_top_level_await` now uses `asyncio.timeout(self.tla_timeout)`
  - Added unit tests that verify override and timeout behavior

- Broaden blocking I/O detection configurability and telemetry (DONE)
  - Introduced internal DetectionPolicy with safe defaults and override injection via constructor/factory
  - Added `ast_cache_max_size` constructor knob with env override `ASYNC_EXECUTOR_AST_CACHE_SIZE`; `None` disables cache
  - Added structured counters in `stats` (detected_blocking_import, detected_blocking_call, missed_attribute_chain) and logs include execution_id
  - Added unit tests for detection breadth, policy knobs, and cache behavior

- Compile consistency (DONE)
  - Switched NamespaceManager compile calls to `dont_inherit=False` to align with cooperative cancellation guidance
