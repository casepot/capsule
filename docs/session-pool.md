# Session Pool

> Status: Authoritative reference for `SessionPool` orchestration and roadmap (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if code has drifted, double-check the current sources on your working commit, capture differences that affect your task, and raise any doc gaps to the user while you proceed with up-to-date information).

## Purpose
`SessionPool` maintains a fleet of subprocess-backed `Session` instances so callers can acquire a ready-to-use worker without paying interpreter startup and warmup cost on every execution. It owns queueing for idle vs. active sessions, the background warmup loop that keeps a configured watermark of ready workers, and the health-check loop that recycles idle processes once they are stale or unhealthy (`src/session/pool.py:29-613`). The pool composes with the session runtime: each `Session` tracks executability, last-use timestamps, and execution counters that the pool uses to enforce recycling and idle eviction policies (`src/session/manager.py:46-458`).

The pool never touches worker transports directly; instead it instantiates `Session` objects and relies on their lifecycle APIs (`start()`, `restart()`, `shutdown()`, `terminate()`) to keep the single-reader invariant intact (`src/session/pool.py:315-366`, `src/session/manager.py:123-705`). This separation lets the pool remain event-driven and makes it safe to run warmup and health workers alongside user-triggered acquisitions without cross-task deadlocks.

## Configuration
`PoolConfig` is a dataclass that records the pool’s operating envelope and provides conservative defaults suitable for development: maintain two warm sessions (`min_idle=2`), cap the fleet at ten (`max_sessions=10`), recycle idle sessions after five minutes (`session_timeout=300.0`), and optionally run startup warmup code inside each session (`warmup_code=None` by default) (`src/session/pool.py:16-27`). The constructor accepts either a `PoolConfig` instance or keyword overrides, including legacy aliases `min_size`/`max_size` that map to the min/max watermark (`src/session/pool.py:32-71`).

Additional knobs control background behavior:
- `health_check_interval` defaults to 30 s but is normalized to a 60 s baseline timer to reduce needless polling while retaining the ability to trigger immediate checks via events (`src/session/pool.py:24-25`, `src/session/pool.py:615-662`).
- `pre_warm_on_start` ensures `start()` calls `ensure_min_sessions()` and primes the warmup worker to replenish the idle queue as soon as a session is acquired (`src/session/pool.py:83-99`, `src/session/pool.py:411-453`).
- `recycle_after_executions` defines the maximum number of user executions per session before the pool restarts it in-place, leveraging `Session.info.execution_count` which increments under the session lock on every `execute()` call (`src/session/pool.py:25-26`, `src/session/pool.py:240-304`, `src/session/manager.py:375-458`).

`SessionPool.__init__` stores configuration in `_config`, prepares the idle/active bookkeeping structures, and creates `asyncio.Event` instances that drive warmup and health loops without relying on sleep-based polling (`src/session/pool.py:72-81`).

## Acquisition Flow
`acquire()` is an event-driven loop that prefers idle sessions, falls back to creating new ones up to `max_sessions`, and finally waits for a release if the fleet is saturated (`src/session/pool.py:130-238`). Successful acquisitions take the session from `_idle_sessions`, confirm it is still alive, and move it into the active set under `_lock` so concurrent health or warmup tasks cannot recycle it mid-use (`src/session/pool.py:147-170`). Metrics capture attempts, hits vs. misses, and the total time spent acquiring (`src/session/pool.py:142-233`). The method honors an optional timeout by calculating a deadline and using `asyncio.wait_for` around the idle queue get; it raises `TimeoutError` once the deadline elapses and records the timeout in metrics (`src/session/pool.py:209-220`).

If no idle session is available and capacity remains, the pool creates a placeholder entry under `_lock`, instantiates a new `Session`, and starts it outside the lock to avoid await-in-lock deadlocks. On success the placeholder is swapped for the real session and the caller receives it immediately; on failure the placeholder is removed so concurrent operations do not perceive a phantom slot (`src/session/pool.py:178-207`, `src/session/pool.py:315-348`). When the pool is shutting down, `acquire()` raises `RuntimeError` so callers can propagate shutdown semantics (`src/session/pool.py:238`).

`release()` removes the session from the active set, enforces the recycle budget, and decides whether the session can re-enter the idle queue (`src/session/pool.py:240-304`). Sessions that have exceeded `recycle_after_executions` are restarted via `Session.restart()`, and those that report `ERROR` or fail the `is_alive` check are either restarted (if `restart_if_dead` is `True`) or removed from the pool entirely with `_remove_session()`, which terminates the subprocess and cleans up state (`src/session/pool.py:252-293`, `src/session/pool.py:350-378`, `src/session/manager.py:692-705`). Every release triggers a health-check signal so idle eviction runs promptly after workload changes (`src/session/pool.py:294-304`).

`stop()` flips `_shutdown`, cancels both background tasks with suppression for `CancelledError`, and concurrently calls `Session.shutdown()` on all tracked sessions to ensure warm processes terminate cleanly before clearing bookkeeping structures (`src/session/pool.py:101-129`, `src/session/manager.py:606-690`).

## Warmup Worker
Operators can call `ensure_min_sessions()` to synchronously bring the pool up to its minimum watermark; `start()` does this automatically when `pre_warm_on_start` is enabled (`src/session/pool.py:83-99`, `src/session/pool.py:411-453`). The helper samples current idle and total counts under `_lock`, spawns `_create_and_add_session()` tasks for each missing slot outside the lock, and gathers results to record how many sessions were successfully created (`src/session/pool.py:415-453`).

The `_warmup_worker()` coroutine blocks on the `_warmup_needed` event, which callers set whenever they consume an idle session or remove one due to health enforcement (`src/session/pool.py:463-555`). When triggered, the worker repeatedly checks pool size under `_lock`, fans out creation tasks to fill the deficit, and yields to the event loop between batches. If every attempt fails it backs off for 500 ms before releasing the event so other triggers can schedule a retry (`src/session/pool.py:479-533`). The worker increments counters for triggers, loop iterations, and warmup-created sessions so operators can measure how often the pool had to replenish itself (`src/session/pool.py:523-549`).

## Health Check Worker
The health worker combines event-driven triggers (`_health_needed`) with a baseline timer that defaults to 60 s to ensure periodic hygiene even if no workload changes occur (`src/session/pool.py:615-662`). Each iteration waits for either the timer or a trigger, clears the event if set, cancels whichever task did not run, and then calls `_run_health_check_once()` (`src/session/pool.py:628-651`). Errors are logged and result in a one-second backoff to avoid thrashing (`src/session/pool.py:658-661`).

`_run_health_check_once()` drains the idle queue into a temporary list, examines each session, and decides whether to recycle it. Idle sessions that have exceeded `session_timeout` (based on `Session.info.last_used_at`) are removed; dead sessions are terminated immediately; everything else is returned to the idle queue (`src/session/pool.py:569-608`, `src/session/manager.py:81-122`). Health-driven removals increment dedicated metrics and trigger warmup so the watermark is restored after evictions (`src/session/pool.py:608-613`).

## Metrics & Observability
`SessionPool` tracks a `PoolMetrics` dataclass that counts both lifecycle events and background worker activity (`src/session/pool.py:747-773`). Acquisition attempts, successes, timeouts, and total latency feed hit-rate and average acquisition calculations in `get_metrics()` (`src/session/pool.py:668-695`). Warmup metrics cover trigger counts, loop iterations, and how many sessions were created by background replenishment, while health metrics capture trigger frequency, runs, and how many sessions were removed for health reasons (`src/session/pool.py:668-742`).

`get_info()` snapshots the current configuration, idle/active/total counts, and the computed metrics so callers can export them to diagnostics surfaces or dashboards (`src/session/pool.py:697-743`). Because metrics are plain attributes on `PoolMetrics`, updates happen in the same coroutine that performed the work; there is currently no dedicated lock protecting increments, which is acceptable in the single-threaded asyncio model but documented as a hardening target in POOL-011 (#50) when richer telemetry and potential cross-thread access arrive (`src/session/pool.py:334-367`, `src/session/pool.py:449-523`).

Structured logs accompany major transitions: session creation, removal, recycling, restart attempts, warmup activation, and health completions all emit `logger.info`/`logger.debug` entries annotated with session identifiers so operators can spot churn or failure patterns quickly (`src/session/pool.py:201-304`, `src/session/pool.py:336-339`, `src/session/pool.py:477-568`).

## Known Limitations
- Warm imports are limited to a single `warmup_code` string executed inside each session; there is no first-class support for per-module warm imports, failure accounting, or latency tracking. Planned work in [POOL-010 (#29)](https://github.com/casepot/capsule/issues/29) will add structured warm import configuration, metrics, and logging to address this gap (`src/session/pool.py:16-71`).
- Health checks only enforce idle timeouts and dead-session removal. Memory usage from session heartbeats is recorded on `Session.info` but unused today, leaving long-lived idle sessions to accumulate RSS until the timeout expires (`src/session/manager.py:46-247`).
- Metrics increments are not synchronized under a dedicated lock, so the counts can drift if future callers update metrics from threads or reentering coroutines; [POOL-011 (#50)](https://github.com/casepot/capsule/issues/50) tracks the circuit breaker work that will add a metrics lock while hardening creation failure backoff (`src/session/pool.py:334-523`).

## Planned Enhancements
- **Warm imports & memory budgets** — POOL-010 is scoped to let operators declare warm imports, enforce idle-memory budgets, and expose corresponding metrics via `get_info()`. Expect new config fields, per-session warm import helpers, and eviction logic that leverages `Session.info.memory_usage` once this lands ([#29](https://github.com/casepot/capsule/issues/29)).
- **Circuit breaker & metrics locking** — POOL-011 introduces a pooled session creation circuit breaker with exponential backoff and synchronized metrics updates so repeated spawn failures cannot overwhelm the host. It will also expose breaker state via `get_info()` for observability ([#50](https://github.com/casepot/capsule/issues/50)).
- **Diagnostics integration** — OBS-011 tracks exposing pool health and warmup status through the broader diagnostics API so operators can inspect pool state remotely without scraping raw logs ([#41](https://github.com/casepot/capsule/issues/41)).

These items are planned and not yet shipped; the sections above describe current behavior.

## Source References
- `src/session/pool.py:16-773`
- `src/session/manager.py:46-705`

## Legacy Material to Supersede
- `docs/_legacy/architecture/session-pool-architecture.md` (retain for historical context only; migrate any missing behavior into this guide if you encounter gaps).

## Open Tasks
- Document and sample the upcoming warm import and memory budget knobs once POOL-010 merges ([#29](https://github.com/casepot/capsule/issues/29)).
- Update metrics documentation after the circuit breaker and metrics lock land in POOL-011 ([#50](https://github.com/casepot/capsule/issues/50)).
- Incorporate diagnostics surfaces once OBS-011 publishes the pool status endpoint ([#41](https://github.com/casepot/capsule/issues/41)).
