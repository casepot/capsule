  Phase 3 Goals

  - Native AsyncExecutor for TLA/async paths (no ThreadedExecutor for those).
  - Compile-first TLA using PyCF_ALLOW_TOP_LEVEL_AWAIT; minimal AST wrapper only as resilience.
  - Coroutine/cancellation lifecycle management and event loop coordination.
  - Blocking I/O detection breadth + telemetry and config.
  - Caching for compiled code objects; PEP 657 location mapping for transforms.
  - Operational refinements: bounded routing concurrency, interceptor budgets, bridge shutdown.

  PR 1 — AsyncExecutor: Native TLA Core (compile-first)

  - Scope
      - Finalize compile-first TLA execution in src/subprocess/async_executor.py without ThreadedExecutor for TLA paths; keep AST fallback minimal only when compile-first fails.
      - Preserve namespace semantics: locals-first merge, then global diffs; record expression results via NamespaceManager.record_expression_result.
  - Key changes
      - Keep and harden _execute_top_level_await (already present and mostly correct).
      - Ensure consistent eval/exec handling: try eval+flags first (to preserve expression result), fall back to exec+flags only when required.
      - Always bind to live namespace mapping; snapshot globals for diffs; never replace mapping.
      - Use asyncio.timeout(self.tla_timeout), preserve/extend exception notes (execution id, snippet).
  - Tests
      - Update/expand tests/unit/test_top_level_await.py to validate compile-first path for assignment and pure expressions; multiple awaits; f-strings; comprehensions; ensure _ history updates.
      - Validate locals-first then global-diff merge under both eval and exec flows.
  - Success criteria
      - All TLA unit tests pass; expression results recorded; no global mapping replacement; AST fallback used only when compile-first SyntaxError occurs.
  - Changelog
      - After PR acceptance, update `docs/PHASE_3_CHANGELOG.md` with a concise summary of behavior changes, tests, and any notable decisions.

  Note: Maintain the Phase 3 changelog after each PR is successfully validated and accepted.

  PR 2 — AsyncExecutor: Native Simple Sync + Async Def (no delegation)

  - Scope
      - Execute simple sync and async-def defining code natively in AsyncExecutor (no delegation to ThreadedExecutor), reserving delegation for true blocking I/O.
  - Key changes
      - Add _execute_simple_sync and “async-def defining” execution path using compile(..., mode='exec'); preserve namespace merge semantics.
      - Keep “blocking” delegation as-is for now (still uses ThreadedExecutor).
  - Tests
      - Adjust tests/unit/test_async_executor.py to remove assertions that simple sync code delegates to ThreadedExecutor.
      - Add tests that native exec preserves namespace identity and results for mixed sequences (sync → async → sync).
  - Success criteria
      - No delegation on simple sync and async-def-defining code paths; namespace object identity remains stable across runs.

  PR 3 — AsyncExecutor: AST Fallback Wrapper, Minimal and PEP 657-aligned

  - Scope
      - Limit transforms to a minimal async wrapper function only; remove broad “def→async def” conversions by default; keep zero-arg lambda→async helper behind a disabled-by-default flag.
  - Key changes
      - Strip or flag off the current transform that rewrites def→async def when _contains_await (default OFF).
      - Keep wrapper shape that preserves original order; inject return locals() for statements; use copy_location and fix_missing_locations; do not reorder user statements.
  - Tests
      - Expand AST fallback tests to confirm minimal wrapper behavior; ensure location info in tracebacks maps correctly (PEP 657 expectations).
  - Success criteria
      - AST fallback is minimal and semantics-preserving by default; location mapping and error spans are correct.

  PR 4 — Coroutine Lifecycle + Cancellation Management

  - Scope
      - Introduce an internal CoroutineManager (lightweight) for AsyncExecutor to track the top-level coroutine and provide a cooperative cancel API; ensure cleanup is reliable.
  - Key changes
      - Track the coroutine returned by eval/exec; close on completion/error.
      - Provide AsyncExecutor.cancel_current() which cancels the pending top-level coroutine/task, recording metrics; do not try to cancel user-launched background tasks.
      - Add basic “cancelled” telemetry counters; structure exception add_notes for cancellation context.
  - Tests
      - New unit tests: long-running await cancels cooperatively; cleanup still occurs on error and cancel; no coroutine leaks.
  - Success criteria
      - Cancelling an in-flight TLA run interrupts promptly; cleanup_coroutines() returns 0 afterward; tests validate cooperative cancel path.

  PR 5 — Blocking I/O Detection Refinements + Telemetry

  - Scope
      - Harden detection breadth and reduce false positives: attribute chain resolution, alias tracking, overshadowing; expose config knobs and counters.
  - Key changes
      - Build on current _contains_blocking_io (already has alias and attribute chain resolution).
      - Add overshadowing checks (user requests = object() shouldn’t signal blocking); per-module method lists remain configurable; add structured counters and optional warnings.
  - Tests
      - tests/unit/test_async_executor_detection_breadth.py: add overshadowing tests; alias from imported names; deep attribute chains like socket.socket().recv.
      - Validate counters (detected_blocking_import/call; missed_attribute_chain ≤ expected).
  - Success criteria
      - Detection covers common patterns with fewer false positives; config toggles work; telemetry counters increment as expected.

  PR 6 — Code Object LRU Cache (compile cache)

  - Scope
      - Add a compiled-code LRU cache keyed by (source, mode, flags) to skip recompile; keep AST cache only for transform cases.
  - Key changes
      - New cache in AsyncExecutor (small default size, configurable; reuse existing env override pattern used by AST cache).
      - Do not cache in error cases; differentiate eval vs exec and flags; clear strategy is LRU.
  - Tests
      - New unit tests verifying cache reuse, keying correctness, and eviction behavior.
  - Success criteria
      - Repeated code paths get faster; cache key correctness validated.

  PR 7 — Optional Symtable-backed Hoisting (feature flag, default OFF)

  - Scope
      - Add a guarded feature to hoist safe, unconditional top-level imports/defs ahead in wrapper compilation without reordering relative import/def order; default OFF.
  - Key changes
      - Use symtable to identify safe bindings; maintain original relative order; treat TypeAlias as assignment-like; do nothing unless flag is enabled.
  - Tests
      - Corpus tests: simple imports/defs hoist successfully; conditional or shadowed defs are not hoisted; semantics preserved with/without flag.
  - Success criteria
      - Feature behind flag; semantics preserved; tests green; documentation clarifies OFF by default.

  PR 8 — Event Loop Coordinator (small, guardrails and docs)

  - Scope
      - Provide a tiny EventLoopCoordinator for AsyncExecutor that standardizes “you must call from a running loop” errors and queues any optional executor internal coroutines; durable functions still must not manage loops.
  - Key changes
      - Add a helper to detect running loop and raise clear guidance; optionally queue internal non-critical coros (diagnostics) for later flush in tests only.
  - Tests
      - tests/unit/test_event_loop_handling.py updated for clearer error messages and nested async contexts.
  - Success criteria
      - Clear, deterministic errors when called out-of-loop; no loop creation performed by AsyncExecutor.

  PR 9 — Operational Refinements: Session Routing Concurrency + Interceptor Budgets

  - Scope
      - Bound routing task concurrency and add interceptor timing budgets; structured warnings on overruns; maintain single-loop invariant.
  - Key changes
      - In src/session/manager.py: add optional max_routing_concurrency (Semaphore) around _route_message task creation; collect basic durations for interceptors and log slow-call warnings (configurable budget, e.g., 10ms).
  - Tests
      - Stress test: flood of outputs doesn’t starve routing; assert that routing doesn’t leak tasks; interceptors exceeding budget raise warnings but do not break routing.
  - Success criteria
      - No regressions; routing remains stable under burst; slow interceptors visible via logs.

  PR 10 — Bridge Lifecycle: close()/cancel_all(), HWM metric exposure

  - Scope
      - Add lifecycle to ResonateProtocolBridge for cancelling timeouts and clearing pending; expose HWM via getter.
  - Key changes
      - Implement close()/cancel_all() to cancel timeout tasks and reject pending with a canned shutdown error; expose pending_high_water_mark().
      - Wire DI shutdown path to call bridge.close() in resonate_init.
  - Tests
      - Unit tests to verify pending cleanup and rejection; race tests rewritten to event-based synchronization (no sleeps).
  - Success criteria
      - No pending correlations left after close(); race tests deterministic; HWM getter returns expected values.

  PR 11 — Documentation + Spec Alignment + Config Knobs

  - Scope
      - Update docs under docs/async_capability_prompts/current/ with final decisions:
      - Compile-first policy (3.11–3.13), minimal AST fallback, transforms OFF by default.
      - Blocking I/O detection config; caching; loop ownership; interceptor budgets.
  - Update API reference with final AsyncExecutor constructor knobs and behavior.
  - Key changes
      - Refresh 10/20/22/24/25 docs to reflect implemented behaviors; mark previous TODOs addressed.
  - Tests
      - None (docs only); ensure lint/type/docs checks pass.
  - Success criteria
      - Docs clearly match implementation; reviewers sign off on spec parity.

  PR 12 — Benchmarks + CI Guardrails (optional stretch within Phase 3)

  - Scope
      - Add light microbenchmarks as tests or separate script to validate perf targets and cache effects; put simple thresholds in comments (no flaky asserts).
  - Key changes
      - Benchmark TLA on no-op and small awaits; repeated compile caching; routing throughput under bursts.
  - Tests
      - Non-flaky microbenchmarks behind a -m perf marker (opt-in).
  - Success criteria
      - Baseline numbers captured; later phases can track regressions.

  Cross-Cutting Concerns

  - Single-loop invariant: keep session as the only transport reader; interceptors remain non-blocking; bridge never reads.
  - Namespace policy: never replace dict; locals-first then global diffs; preserve ENGINE_INTERNALS.
  - Error semantics: use exception notes with execution id/snippets; AST wrapper preserves PEP 657 spans.
  - Config surfaces: timeouts, cache sizes, blocking detection modules/methods, warning toggles, interceptor budgets, routing concurrency limit.

  Workloads & Testing Summary

  - Unit
      - AsyncExecutor TLA (eval/exec), AST fallback, globals binding, result history, caching keys, detection breadth/false positives, cancellation/cleanup.
      - Bridge correlation + lifecycle, pending/timeouts, race determinism.
      - Session routing semaphore + interceptor budget warnings.
  - Integration
      - End-to-end worker/session remains ThreadedExecutor-based; ensure Phase 2b/2c invariants hold (output-before-result, Busy guard, checkpoint/restore logic).
      - Do not introduce competing readers; continue using interceptors in integration tests.
  - Performance
      - Validate cache win in unit-level measures (short loops); optional perf marker in CI.

  Justifications

  - Narrow, compile-first approach avoids semantic drift and keeps error locations correct; matches Python 3.11–3.13 capabilities.
  - Removing (or disabling) broad def→async transforms reduces risk; fallback wrapper suffices for resilience.
  - Native simple/async-def execution avoids ThreadedExecutor overhead; blocking I/O still delegates safely.
  - Coroutine lifecycle + cancel address async-specific concerns that ThreadedExecutor’s sync cancellation cannot.
  - Operational caps (routing concurrency; interceptor budgets) improve resilience under load without architectural churn.

  Dependencies & Sequencing

  - PRs 1–3 must go first (core execution semantics).
  - PRs 4–6 can proceed after 1–3; 7 (hoisting) is optional and behind a flag.
  - PRs 8–10 are operational and can be parallelized after 2; merge after focused review.
  - PR 11 can land at the end; PR 12 is optional.

  Success Criteria (Phase 3 overall)

  - AsyncExecutor runs TLA/async-def and simple sync natively; ThreadedExecutor only for blocking sync.
  - Minimal AST fallback only; transforms OFF by default; correct error spans.
  - Cancellation works for async; no coroutine leaks.
  - Blocking I/O detection broadened with fewer false positives; telemetry present.
  - Code-object caching speeds repeated runs; cache keys distinguish (source, mode, flags).
  - Session routing remains stable; interceptor slow calls visible; bridge lifecycle implemented.

  Reading Guide Per PR (Phase 3)

  PR 1 — AsyncExecutor: Native TLA Core (compile-first)
  - Read
      - FOUNDATION_FIX_PLAN.md (Phase 3: Full AsyncExecutor Implementation; Research‑Informed Updates)
      - docs/async_capability_prompts/current/22_spec_async_execution.md (TLA compile matrix; CO_COROUTINE checks; eval vs exec; PEP 657)
      - docs/async_capability_prompts/current/24_spec_namespace_management.md (merge‑only; locals‑first then global diffs; history)
      - docs/async_capability_prompts/current/20_spec_architecture.md (compile‑first + minimal transform policy; single‑loop invariant)
      - docs/async_capability_prompts/current/25_spec_api_reference.md (AsyncExecutor API/config notes)
      - Source: src/subprocess/async_executor.py, src/subprocess/namespace.py
      - Tests: tests/unit/test_top_level_await.py; tests/unit/test_async_executor_namespace_binding.py; tests/unit/test_event_loop_handling.py
  - Glean
      - Prefer compile‑first with flags; await coroutine result; record expression results; merge locals then global diffs; keep PEP 657 spans; enrich exceptions with notes

  PR 2 — AsyncExecutor: Native Simple Sync + Async Def
  - Read
      - FOUNDATION_FIX_PLAN.md (Phase 3 native async path; delegation reserved for blocking)
      - docs/async_capability_prompts/current/22_spec_async_execution.md (Execution Mode Detection; Core Execution Methods)
      - docs/async_capability_prompts/current/10_prompt_async_executor.md (design + routing)
      - docs/async_capability_prompts/current/24_spec_namespace_management.md (merge‑only semantics)
      - Source: src/subprocess/async_executor.py; reference src/subprocess/executor.py
      - Tests: tests/unit/test_async_executor.py; tests/unit/test_namespace_merge.py
  - Glean
      - Run simple/defining code natively; preserve namespace identity; keep delegation strictly for blocking sync

  PR 3 — Async Fallback Wrapper (minimal)
  - Read
      - FOUNDATION_FIX_PLAN.md (no mass transforms; wrapper only; PEP 657)
      - docs/async_capability_prompts/current/22_spec_async_execution.md (AST Fallback; Location Mapping)
      - docs/async_capability_prompts/current/24_spec_namespace_management.md (locals‑first then global diffs on fallback)
      - Source: src/subprocess/async_executor.py (transform site)
      - Tests: tests/unit/test_top_level_await.py; tests/unit/test_async_executor.py (AST)
  - Glean
      - Keep wrapper minimal; don’t reorder; preserve error spans; avoid broad def→async unless flagged

  PR 4 — Coroutine Lifecycle + Cancellation
  - Read
      - FOUNDATION_FIX_PLAN.md (CoroutineManager; ExecutionCancellation; metrics)
      - docs/async_capability_prompts/current/22_spec_async_execution.md (Event loop coord; TaskGroup; timeout)
      - Source: src/subprocess/async_executor.py; src/session/manager.py (cancel/interrupt); src/subprocess/worker.py (cancel interplay)
      - Tests: tests/features/test_cancellation.py; tests/features/test_event_driven.py; tests/unit/test_executor.py (cancellation components)
  - Glean
      - Track top-level coroutine; cancel cooperatively; cleanup reliably; simple counters for visibility

  PR 5 — Blocking I/O Detection + Telemetry
  - Read
      - FOUNDATION_FIX_PLAN.md (detection breadth; telemetry; config)
      - docs/async_capability_prompts/current/22_spec_async_execution.md (blocking indicators; attribute chains)
      - Source: src/subprocess/async_executor.py (_contains_blocking_io; policy)
      - Tests: tests/unit/test_async_executor_detection_breadth.py; tests/unit/test_async_executor.py (telemetry)
  - Glean
      - Resolve attribute bases with alias mapping; guard overshadowing; expose config; optional warnings; counters for imports/calls

  PR 6 — Code Object LRU Cache
  - Read
      - FOUNDATION_FIX_PLAN.md (code‑object caching keyed by source+mode+flags)
      - docs/async_capability_prompts/current/22_spec_async_execution.md (Caching Strategy)
      - Source: src/subprocess/async_executor.py
      - Tests: tests/unit/test_async_executor_ast_cache_config.py (pattern); add code‑object cache tests
  - Glean
      - LRU keyed by (source, mode, flags); avoid caching failures; keep AST cache only for transformed trees

  PR 7 — Optional Symtable Hoisting (flagged)
  - Read
      - FOUNDATION_FIX_PLAN.md (symbol‑aware hoisting — optional)
      - docs/async_capability_prompts/current/22_spec_async_execution.md (AST coverage + hoisting cautions)
      - Source: src/subprocess/async_executor.py
      - Tests: add new ON/OFF hoisting tests
  - Glean
      - Hoist safe, unconditional defs/imports only; preserve order; keep OFF by default

  PR 8 — Event Loop Coordinator
  - Read
      - FOUNDATION_FIX_PLAN.md (EventLoopCoordinator goals)
      - docs/async_capability_prompts/current/22_spec_async_execution.md (Event Loop Considerations; asyncio.timeout usage)
      - Source: src/subprocess/async_executor.py
      - Tests: tests/unit/test_event_loop_handling.py
  - Glean
      - Standardize error surfaces for missing loop; never create loops; optionally queue internal diagnostics in tests only

  PR 9 — Session Routing Concurrency + Interceptor Budgets
  - Read
      - FOUNDATION_FIX_PLAN.md (Operational refinements)
      - docs/async_capability_prompts/current/20_spec_architecture.md (single‑loop; interceptors)
      - Source: src/session/manager.py (_receive_loop; _route_message)
      - Tests: add unit/integration for semaphore + slow interceptor warnings
  - Glean
      - Bound routing task fan‑out; measure interceptor durations; warn on overruns; no routing regressions

  PR 10 — Bridge Lifecycle (close/cancel_all; HWM)
  - Read
      - FOUNDATION_FIX_PLAN.md (bridge lifecycle; DI shutdown; race determinsm)
      - docs/async_capability_prompts/current/25_spec_api_reference.md (bridge correlation + timeout)
      - Source: src/integration/resonate_bridge.py; src/integration/resonate_init.py
      - Tests: tests/unit/test_resonate_protocol_bridge.py; tests/unit/test_resonate_protocol_bridge_race.py
  - Glean
      - Cancel timeouts; reject pending on close; expose pending HWM; keep single‑loop ownership

  PR 11 — Docs + Spec Alignment
  - Read
      - FOUNDATION_FIX_PLAN.md (Phase 3 + Architecture Alignment)
      - docs/async_capability_prompts/current/{10,20,22,24,25}_*.md
  - Glean
      - Document compile‑first policy; fallback limits; detection config; caching; loop ownership; routing/budgets; API defaults

  PR 12 — Benchmarks + CI Guardrails (optional)
  - Read
      - FOUNDATION_FIX_PLAN.md (Performance & observability)
      - docs/async_capability_prompts/current/20_spec_architecture.md (performance targets)
      - Source: src/subprocess/async_executor.py; src/session/manager.py
      - Tests/Benches: add opt‑in perf markers (-m perf)
  - Glean
      - Baseline TLA latency and caching wins; no flaky thresholds
