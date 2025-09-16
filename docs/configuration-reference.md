# Configuration Reference

> Status: Authoritative reference for runtime configuration surfaces (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if code has drifted, double-check the current sources on your working commit, capture differences that affect your task, and raise any doc gaps while you proceed with up-to-date information).

## Purpose
- Document the knobs that currently shape session lifecycle, pooling, and executor behavior so operators know which defaults Capsule ships today.
- Call out precedence rules (constructor args vs dataclass defaults vs environment variables) for each surface.
- Track upcoming configuration work so teams can coordinate rollouts without searching through issues.

## Session Configuration

### Current behavior
| Field | Default (source) | Current effect |
| --- | --- | --- |
| `enable_metrics` | `False` (`src/session/config.py:14`) | Enables cancellation counters when `Session` waits on queues; the counters stay zero unless this flag is true (`src/session/manager.py:353`). |
| `default_execute_timeout` | `30.0` (`src/session/config.py:17`) | Not yet consumed; `Session.execute()` still hard-codes a `timeout` parameter default of 30 s (`src/session/manager.py:378`) and callers pass an explicit timeout when needed. |
| `ready_timeout` | `10.0` (`src/session/config.py:18`) | Currently unused; worker readiness waits are still hard-coded to 10 s via `asyncio.wait_for` inside `Session.start()` (`src/session/manager.py:155`). |
| `shutdown_timeout` | `5.0` (`src/session/config.py:19`) | Currently unused; graceful shutdown waits 5 s via a literal in `Session.shutdown()` (`src/session/manager.py:637`). |

Additional notes:
- Sessions accept an optional `SessionConfig`; omitting it creates a fresh copy of the dataclass so per-session tweaks do not bleed across instances (`src/session/manager.py:68`).
- Metrics recorded when `enable_metrics` is true are stored alongside other session info and surfaced through diagnostic hooks (e.g., `_metrics["cancel_event_triggers"]`) (`src/session/manager.py:353`).

### Planned updates
- `EW-012 — Worker/Executor: Plumb timeouts/pump policy from SessionConfig` will extend the dataclass with an executor-specific block and propagate overrides to the subprocess via environment variables, aligning the ready/shutdown defaults with configurable values ([#49](https://github.com/casepot/capsule/issues/49)). The issue covers explicit logging of applied settings and tests for shortened input timeouts.

## Session Pool Configuration

### Current behavior
| Field | Default (source) | Current effect |
| --- | --- | --- |
| `min_idle` | `2` (`src/session/pool.py:20`) | `SessionPool.ensure_min_sessions()` creates new sessions until at least this many are idle, respecting `max_sessions` (`src/session/pool.py:411`). |
| `max_sessions` | `10` (`src/session/pool.py:21`) | `_create_session()` refuses to spawn when the pool already tracks this many sessions (`src/session/pool.py:317`). |
| `session_timeout` | `300.0` s (`src/session/pool.py:22`) | Idle sessions exceeding the timeout are removed during health checks (`src/session/pool.py:591`). |
| `warmup_code` | `None` (`src/session/pool.py:23`) | Non-null code is passed to each `Session` so it runs immediately after startup (`src/session/pool.py:324`). |
| `health_check_interval` | `30.0` s (`src/session/pool.py:24`) | The hybrid health worker treats the default as a hint and stretches it to 60 s for efficiency unless overridden (`src/session/pool.py:624`). |
| `pre_warm_on_start` | `True` (`src/session/pool.py:25`) | Startup pre-heats `min_idle` sessions and primes the warmup worker before returning (`src/session/pool.py:92`). |
| `recycle_after_executions` | `100` (`src/session/pool.py:26`) | Sessions reaching the threshold are recycled on release with a fresh subprocess (`src/session/pool.py:252`). |

Additional notes:
- The constructor accepts keyword overrides even without a `PoolConfig`; legacy aliases `min_size`/`max_size` still point to the modern fields for backward compatibility (`src/session/pool.py:51`).
- Pool metrics accumulate on the `PoolMetrics` dataclass and are exposed via `get_info()` along with the active config (`src/session/pool.py:709`).

### Planned updates
- `POOL-010 — SessionPool with Pre-Warm & Imports (Finalize)` expands `PoolConfig` with structured warm-import and memory budget fields so operators can control module preload, RSS eviction thresholds, and related metrics ([#29](https://github.com/casepot/capsule/issues/29)).
- `POOL-011 — SessionPool: Circuit breaker for create failures + metric safety` introduces breaker parameters (threshold, cooldown, backoff) and synchronized metric updates to avoid thundering herds during repeated spawn failures ([#50](https://github.com/casepot/capsule/issues/50)).

## Executor Configuration

### ThreadedExecutor and worker defaults
- `ThreadedExecutor` parameters are currently only set via its constructor: queue maximum (`1024`), backpressure policy (`"block"`), chunk size (`64 KiB`), drain timeout (`2000` ms), input send/response timeouts (`5` s / `300` s), cancellation interval (`100`), and cooperative cancellation (`True`) (`src/subprocess/executor.py:259`).
- `SubprocessWorker.execute()` instantiates the executor with the transport, namespace, and loop while overriding only the input timeouts (5 s send, 300 s wait); drain-before-result still uses a hard-coded 5 s limit on the worker side (`src/subprocess/worker.py:282`, `src/subprocess/worker.py:337`).
- The async compatibility wrapper suppresses drain timeouts regardless of configuration, logging a warning only once per executor lifetime (`src/subprocess/executor.py:795`).

### AsyncExecutor and DI surfaces
- The constructor exposes knobs for top-level await timeout, AST cache size, blocking-detection overrides, overshadow guard, import requirements, optional AST rewrites, and fallback linecache capacity (`src/subprocess/async_executor.py:228`).
- Environment variables fill in defaults when the constructor leaves parameters at their shipped values: cache size from `ASYNC_EXECUTOR_AST_CACHE_SIZE`, def→async and async-lambda transforms from `ASYNC_EXECUTOR_ENABLE_DEF_AWAIT_REWRITE` / `ASYNC_EXECUTOR_ENABLE_ASYNC_LAMBDA_HELPER`, and fallback linecache capacity from `ASYNC_EXECUTOR_FALLBACK_LINECACHE_MAX` (`src/subprocess/async_executor.py:300`, `src/subprocess/async_executor.py:342`, `src/subprocess/async_executor.py:365`).
- `async_executor_factory` bridges dependency injection: explicit arguments win, otherwise the factory inspects `ctx.config` for overrides before falling back to environment variables or constructor defaults (`src/integration/resonate_wrapper.py:104`, `src/integration/resonate_wrapper.py:171`).

### Planned updates
- `EW-012` will define an `ExecutorConfig` nested within `SessionConfig`, emit `WORKER_*`/`EXECUTOR_*` environment variables, and ensure the worker and executor respect those overrides end to end ([#49](https://github.com/casepot/capsule/issues/49)).
- `EW-011 — Executor: Configurable drain-timeout suppression in async wrapper` adds an opt-out flag and `THREAD_EXECUTOR_SUPPRESS_ASYNC_WRAPPER_DRAIN_TIMEOUT` environment control so production paths can fail fast on drain timeouts ([#48](https://github.com/casepot/capsule/issues/48)).
- `EW-010 — Worker: Route TLA/async-def to AsyncExecutor` introduces `WORKER_ENABLE_NATIVE_ASYNC` to select async routing and reuses the output pump so pump configuration applies consistently across execution modes ([#51](https://github.com/casepot/capsule/issues/51)).
- `EW-014 — AsyncExecutor: Code object caching` will add a configurable code cache capacity and `ASYNC_EXECUTOR_CODE_CACHE_SIZE` override alongside cache hit/miss metrics ([#47](https://github.com/casepot/capsule/issues/47)).

## Environment Variables & Feature Flags

### Current flags
| Variable | Accepted values | Effect |
| --- | --- | --- |
| `ASYNC_EXECUTOR_AST_CACHE_SIZE` | Integer (string) | Overrides the AST analysis LRU capacity when the constructor leaves `ast_cache_max_size` at its default (`src/subprocess/async_executor.py:300`). |
| `ASYNC_EXECUTOR_ENABLE_DEF_AWAIT_REWRITE` | Truthy string (`1`/`true`/`yes`) | Enables the guarded AST rewrite that converts `def` with awaits into `async def` when the constructor passes `None` (`src/subprocess/async_executor.py:342`). |
| `ASYNC_EXECUTOR_ENABLE_ASYNC_LAMBDA_HELPER` | Truthy string (`1`/`true`/`yes`) | Enables the lambda helper transform under the same conditions (`src/subprocess/async_executor.py:350`). |
| `ASYNC_EXECUTOR_FALLBACK_LINECACHE_MAX` | Integer (string) | Sets the fallback linecache LRU capacity when not provided explicitly (`src/subprocess/async_executor.py:365`). |

The executor treats any other value (including unset) as “use the shipped default”. There are no `CAPS_ENABLE_*` or worker/session feature flags in the codebase yet.

### Planned flags
Upcoming work introduces additional environment toggles:

- Executor/worker configuration surfaces from `EW-012` (`WORKER_INPUT_SEND_TIMEOUT`, `EXECUTOR_OUTPUT_BACKPRESSURE`, etc.) and the async wrapper suppression flag (`THREAD_EXECUTOR_SUPPRESS_ASYNC_WRAPPER_DRAIN_TIMEOUT`) in `EW-011` ([#49](https://github.com/casepot/capsule/issues/49), [#48](https://github.com/casepot/capsule/issues/48)).
- Async routing enablement via `WORKER_ENABLE_NATIVE_ASYNC` for `EW-010` ([#51](https://github.com/casepot/capsule/issues/51)).
- Display and progress streaming flags from `EW-015` / `EW-016`, including `CAPS_ENABLE_DISPLAY`, `CAPS_DISPLAY_CHUNK_KB`, `CAPS_MAX_DISPLAY_MB`, `CAPS_ENABLE_PROGRESS`, and related queue/rate-limit knobs ([#27](https://github.com/casepot/capsule/issues/27), [#28](https://github.com/casepot/capsule/issues/28)).
- Protocol negotiation and capability caching flags such as `SESSION_ENABLE_PROTOCOL_NEGOTIATION`, `CAPS_ENABLE_IDEMPOTENCY_CACHE`, `CAPS_IDEMP_TTL_SEC`, and streaming controls (`CAPS_ENABLE_STREAMS`, `CAPS_STREAM_WINDOW_SIZE`, `CAPS_STREAM_QUEUE_MAX`) arriving with `PROTO-011` through `PROTO-013` ([#36](https://github.com/casepot/capsule/issues/36), [#37](https://github.com/casepot/capsule/issues/37), [#31](https://github.com/casepot/capsule/issues/31)).
- `ASYNC_EXECUTOR_CODE_CACHE_SIZE` from `EW-014` to manage compiled code caching once that lands ([#47](https://github.com/casepot/capsule/issues/47)).

## Rollout guidance
- Treat constructor overrides as the single source of truth until the new environment plumbing in `EW-012` ships. When you need non-default executor behavior today, supply a tuned `SessionConfig` and instantiate sessions manually rather than relying on unimplemented fields.
- After the new env-driven surfaces land, roll out changes behind their dedicated flags: enable the flag in staging, confirm the worker logs the effective configuration, and watch the executor metrics to verify the override took effect (planned in [#49](https://github.com/casepot/capsule/issues/49)).
- Use `SessionPool.get_info()` to audit pool configuration at runtime; this remains the authoritative snapshot for operations teams (`src/session/pool.py:709`).

## Known gaps / future work
- `SessionConfig` timeout fields are placeholders until `EW-012` threads them through the worker; teams should not assume they alter behavior yet ([#49](https://github.com/casepot/capsule/issues/49)).
- Pool breaker and warm-import/memory-budget controls are tracked in `POOL-010`/`POOL-011`; expect additional `PoolConfig` fields and env knobs once those land ([#29](https://github.com/casepot/capsule/issues/29), [#50](https://github.com/casepot/capsule/issues/50)).
- Feature-flag gating for display, progress, idempotency, streaming, and async routing is pending under `EW-015`, `EW-016`, and the `PROTO` workstream; this document will expand once those environment variables are implemented ([#27](https://github.com/casepot/capsule/issues/27), [#28](https://github.com/casepot/capsule/issues/28), [#36](https://github.com/casepot/capsule/issues/36), [#37](https://github.com/casepot/capsule/issues/37), [#31](https://github.com/casepot/capsule/issues/31), [#51](https://github.com/casepot/capsule/issues/51)).
