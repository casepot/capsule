# Execution Engine

> Status: Authoritative reference for the threaded execution path (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if code has drifted, double-check the current sources on your working commit, capture differences that affect your task, and raise any doc gaps to the user while you proceed with up-to-date information).

## Purpose
The execution engine is the worker-side runtime that coordinates synchronous code execution, output streaming, and protocol I/O inside the subprocess. It combines the `ThreadedExecutor` (thread + pump) with the `SubprocessWorker` control loop to honor Capsule’s single-reader, output-before-result, and merge-only namespace invariants. Use this document when modifying the threaded pipeline, pump/backpressure policy, input shims, or worker orchestration. For native top-level await and coroutine semantics, consult `docs/async-executor.md`; the async executor still delegates blocking and input-heavy code back to the components described here.

## ThreadedExecutor Pipeline
`ThreadedExecutor` consumes a `MessageTransport`, namespace, and the session event loop, then prepares the synchronous execution pipeline with configurable pump controls (`output_queue_maxsize=1024`, default `block` backpressure, 64 KiB line chunking, 2 s drain timeout, input timeouts) and telemetry counters for enqueued/sent/dropped output (`src/subprocess/executor.py:252`). Console output is rerouted through `ThreadSafeOutput`, which normalizes carriage returns, chunks long lines, and pushes `_OutputItem` entries into an asyncio queue guarded by `_FlushSentinel` and `_StopSentinel` markers to delimit drain phases (`src/subprocess/executor.py:93`).

Output produced by user code flows through `_enqueue_from_thread`, which applies the selected backpressure policy: block via a semaphore (`block`), drop immediately (`drop_new`), asynchronously trim the oldest item (`drop_oldest`), or raise `OutputBackpressureExceeded` (`error`). Queue depth, dropped-count metrics, and `mark_not_drained` events are updated in the same path so the pump can report health and unblock flush waiters (`src/subprocess/executor.py:391`). The pump itself is started with `start_output_pump`; it runs an await-driven loop that sends `OutputMessage`s in order, acknowledges flush sentinels by completing their futures, and guarantees `drain_event` is set even when the task exits unexpectedly (`src/subprocess/executor.py:452`). `drain_outputs` inserts a flush sentinel, waits for pump completion, and raises `OutputDrainTimeout` with queue diagnostics if the timeout expires (`src/subprocess/executor.py:509`).

Input handling mirrors this event-driven design. `create_protocol_input` injects a replacement `input()` that writes prompts to stdout, allocates a waiter keyed by a UUID, submits an `InputMessage` via `run_coroutine_threadsafe`, and blocks the worker thread until either the session responds or the configured timeout elapses (`src/subprocess/executor.py:308`). `handle_input_response` resolves the waiter, while `shutdown_input_waiters` cancels them whenever the executor is torn down (`src/subprocess/executor.py:552`).

When `execute_code` runs, it resets the cancellation token, installs the cancel tracer (see below), ensures the namespace exposes a protocol-aware `input`, and replaces `sys.stdout`/`sys.stderr` with pump-backed streams before compiling with `dont_inherit=False` so the tracer is honored in exec/eval frames. It updates the REPL-style `_` history on successful expressions, streams exceptions to stderr, and restores stdout/stderr in a `finally` block without undoing the input shim (`src/subprocess/executor.py:607`). The async compatibility wrapper `execute_code_async` runs this same pipeline inside a threadpool and, for now, suppresses drain timeouts after logging a warning so legacy async tests keep passing (`src/subprocess/executor.py:757`).

## Worker Integration
`SubprocessWorker` owns the subprocess namespace, namespace bookkeeping, and protocol loop. It initializes `ENGINE_INTERNALS` keys in place to preserve REPL state (`src/subprocess/worker.py:120`) and exposes a `start()` handshake that sends `ReadyMessage` capability announcements and spawns a heartbeat task emitting RSS/CPU/namespace metrics every five seconds (`src/subprocess/worker.py:221`).

The main `run()` loop is the sole reader of the transport: it routes `ExecuteMessage`, `InputResponse`, checkpoint/restore, cancel/interrupt, and shutdown messages while maintaining the single-reader invariant (`src/subprocess/worker.py:489`). To keep routing responsive, the worker rejects concurrent executes with a synthetic `Busy` `ErrorMessage` whenever an active executor exists (`src/subprocess/worker.py:514`). `ExecuteMessage` handling constructs a `ThreadedExecutor`, starts its pump, records `_active_executor`/`_active_thread`, optionally captures sources/imports, and spins a daemon thread that invokes `execute_code` (`src/subprocess/worker.py:268`).

While the execution thread runs, the worker polls its liveness with short `asyncio.sleep(0.001)` yields so the message loop can continue handling input responses, cancels, and heartbeats. After the thread joins, the worker enforces output-before-result by awaiting `executor.drain_outputs(timeout=5.0)`; any drain timeout logs a warning, emits an `ErrorMessage` tagged as `OutputDrainTimeout`, and intentionally skips the result to prevent misordered payloads (`src/subprocess/worker.py:333`). Successful completions send structured `ResultMessage`s that include both JSON-safe values and `repr`, while executor-raised exceptions become protocol errors with full tracebacks (`src/subprocess/worker.py:365`). Cleanup always shuts down input waiters, signals the pump to stop, and clears active executor references so the next execution can proceed (`src/subprocess/worker.py:421`).

Beyond execution, the worker translates `InputResponse` messages into executor callbacks, preserving the simple single-executor routing until `FUTURE (#4)` introduces per-execution maps (`src/subprocess/worker.py:520`). It provides lightweight checkpoint/restore handlers that serialize namespace snapshots via `NamespaceManager` while honoring merge-only semantics for `ENGINE_INTERNALS` (`src/subprocess/worker.py:551`). Cancellation messages pass through `_cancel_with_timeout`, which requests cooperative cancellation, waits up to the provided grace period (default 500 ms), and marks the worker unhealthy (triggering restart) if the thread fails to exit (`src/subprocess/worker.py:166`). Interrupts reuse the same cancellation path and optionally exit the worker when `force_restart` is requested (`src/subprocess/worker.py:693`).

## Cancellation & Tracing
Cancellation is coordinated across the worker thread, tracer, and input shim. `CancelToken` exposes an atomic flag guarded by a lock so `ThreadedExecutor.cancel()` can be invoked from any thread; it also wakes pending input waiters to prevent a stuck `input()` call from blocking shutdown (`src/subprocess/executor.py:30`). `_create_cancel_tracer` installs a `sys.settrace` hook that checks the token every `cancel_check_interval` line events (default 100) and raises `KeyboardInterrupt` when set, ensuring Python-level loops can be interrupted without busy-waiting (`src/subprocess/executor.py:53`). `execute_code` compiles with `dont_inherit=False` so the tracer propagates into evaluated frames, and always clears the trace function afterward to avoid leaking instrumentation into future executions (`src/subprocess/executor.py:607`).

On the worker side, `_cancel_with_timeout` calls `executor.cancel()`, mirrors the grace timer while the thread remains alive, and escalates to a hard restart if the cooperative signal fails to finish within the deadline (`src/subprocess/worker.py:166`). This design stops short of pre-empting C extensions or long-running system calls; when cancellation fails, the session restarts the subprocess to regain a clean state. Upcoming AsyncExecutor hardening in `EW-013 (#46)` will close similar races for coroutine paths so cancel requests issued before task registration still take effect, keeping both execution models aligned.

## Drain Timeout Policy
There are two distinct drain policies today. The worker path treats `OutputDrainTimeout` as fatal: it logs the failure, emits an `ErrorMessage`, and withholds the result to guarantee that clients never observe a result before corresponding stdout/stderr chunks (`src/subprocess/worker.py:333`). The async compatibility wrapper used by tests and the AsyncExecutor’s blocking-sync delegation catches the timeout, logs a `drain_timeout_suppressed_in_async_wrapper` warning once per execution, and continues so brittle transports do not break developers (`src/subprocess/executor.py:795`).

The roadmap targets convergence. `EW-011 (#48)` will make the wrapper suppression policy constructor/env-controlled so production callers can opt into strict behavior, while `EW-012 (#49)` carries the worker’s drain timeout, queue size, backpressure, and input timings from `SessionConfig` into the subprocess so operators no longer patch code to tune these limits. Until those land, treat the worker as the source of truth: production executions should run through the worker path so ordering guarantees hold.

## Planned Enhancements
- **Async routing** — `EW-010 (#51)` introduces a gated code path that routes top-level await and async-def code through `AsyncExecutor` while reusing the `ThreadSafeOutput` pump for stdout/stderr. Blocking or `input()` heavy code will continue on the threaded executor.
- **Configuration plumbing** — `EW-012 (#49)` extends `SessionConfig` with executor knobs (timeouts, backpressure, cancel cadence) and teaches the worker to honor them. `EW-011 (#48)` builds on that work to let the async wrapper surface drain timeouts instead of suppressing them by default.
- **Async executor parity** — `EW-013 (#46)` and `EW-014 (#47)` harden coroutine cancellation and add compile caching so AsyncExecutor behaves predictably once the worker begins invoking it. Those improvements reduce divergence between async and thread paths while keeping the pump ordering model unchanged.
- **Structured channels** — Display and progress publishers will reuse the pump and worker routing once `EW-015 (#27)` and `EW-016 (#28)` land. Both are flagged features that add `_DisplayChunk`/`ProgressMessage` handling to the pump and worker loop without violating single-reader or output-before-result guarantees.
- **Input routing** — `FUTURE (#4)` documents a follow-up that replaces the “active executor only” input response routing with an execution-id keyed map, preparing the worker for eventual concurrency.

## Source References
- `src/subprocess/executor.py:30`
- `src/subprocess/executor.py:93`
- `src/subprocess/executor.py:252`
- `src/subprocess/executor.py:308`
- `src/subprocess/executor.py:391`
- `src/subprocess/executor.py:452`
- `src/subprocess/executor.py:509`
- `src/subprocess/executor.py:552`
- `src/subprocess/executor.py:607`
- `src/subprocess/executor.py:757`
- `src/subprocess/worker.py:120`
- `src/subprocess/worker.py:166`
- `src/subprocess/worker.py:221`
- `src/subprocess/worker.py:268`
- `src/subprocess/worker.py:333`
- `src/subprocess/worker.py:365`
- `src/subprocess/worker.py:421`
- `src/subprocess/worker.py:489`
- `src/subprocess/worker.py:514`
- `src/subprocess/worker.py:520`
- `src/subprocess/worker.py:551`
- `src/subprocess/worker.py:693`
- `src/subprocess/constants.py:12`

## Legacy Material to Supersede
The executor notes in `_legacy/async_capability_prompts/current/22_spec_async_execution.md` and the event-driven patterns document describe the pre-pump refactor and poll-heavy routing loops. Treat them solely as historical context and update this guide if you uncover behavior that is still documented only in the archive.
