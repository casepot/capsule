# Diagnostics & Observability

> Status: Authoritative reference for instrumentation, telemetry surfaces, and planned diagnostics work (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if code has drifted, double-check the current sources on your working commit, capture differences that affect your task, and raise any doc gaps to the user while you proceed with up-to-date information).

## Purpose
Capsule’s diagnostics span worker heartbeats, session and pool metrics, execution-engine counters, protocol instrumentation, and bridge breadcrumbs. This guide is the canonical map of those signals and the roadmap items that will turn them into supported tracing and introspection APIs. Use it when wiring monitoring, deciding where to attach structured logging, or planning the upcoming OBS milestones. Architectural context lives in `architecture-overview.md`; execution details live in the subsystem guides cited throughout.

## Existing Telemetry
### Worker process signals
- The subprocess announces capabilities once on startup and emits a five-second heartbeat carrying RSS, CPU percentage, and namespace size so the manager can spot unhealthy workers early (`src/subprocess/worker.py:245`, `src/protocol/messages.py:126`). Failed sends log an error and the loop keeps running to avoid losing the reader.

### Session runtime metrics
- `SessionInfo` tracks lifecycle state, execution counts, and heartbeat-fed resource stats and is exposed through `Session.info` (`src/session/manager.py:45`).
- Opt-in metrics (`SessionConfig.enable_metrics`) count cancel-event activations and executions interrupted by cancellation in the cancellable wait primitive and the execute loop (`src/session/manager.py:353`, `src/session/manager.py:450`).
- Passive message interceptors let callers record additional telemetry without stealing the single-reader role: each interceptor runs on the receive loop before routing and log errors instead of aborting (`src/session/manager.py:262`).
- Today these metrics remain private; the test suite asserts on `session._metrics` directly to guard regressions until OBS-011 formalizes an API (`tests/features/test_event_driven.py:102`).

### Session pool metrics
- `SessionPool` maintains a `PoolMetrics` dataclass covering hit/miss rates, acquisition latency, recycle/restart counts, warmup/health triggers, and derived efficiencies; `get_info()` packages configuration, status, and metrics for callers (`src/session/pool.py:668`, `src/session/pool.py:705`).
- Warmup and health workers increment triggers only when their event flags transition from unset, so counting survives bursty traffic without double-accounting (`src/session/pool.py:548`, `src/session/pool.py:565`).
- Feature tests validate that the info payload exposes warmup and health metrics, again via the private `_metrics` property for now (`tests/features/test_warmup.py:323`, `tests/features/test_health_check.py:336`).

### Execution engine counters
- `ThreadedExecutor` tracks outputs enqueued, sent, dropped, and the max queue depth, giving first-order insight into pump backpressure (`src/subprocess/executor.py:301`).
- Drain timeouts report the number of pending sends, observed queue size, and cumulative sent/dropped counters before raising `OutputDrainTimeout`, which the worker surfaces as an error to preserve output-before-result ordering (`src/subprocess/executor.py:509`).
- The async compatibility wrapper logs `drain_timeout_suppressed_in_async_wrapper` once per execution when it swallows a timeout to keep legacy async tests green, documenting the divergence from worker policy (`src/subprocess/executor.py:802`).

### Async executor stats
- `AsyncExecutor.stats` is a thread-safe dictionary capturing execution counts, blocking-import/call detections, AST fallback rewrites, and cancellation bookkeeping, with a `warn_on_blocking` flag gating noisy warnings for synchronous patterns (`src/subprocess/async_executor.py:311`, `src/subprocess/async_executor.py:580`).
- Execution runs increment counters for successes, errors, and cancellations, and the cancellation path records whether a request was effective or a no-op, allowing tests to assert cooperative shutdown guarantees (`src/subprocess/async_executor.py:801`, `src/subprocess/async_executor.py:1649`, `tests/unit/test_async_executor_cancellation.py:25`).

### Transport instrumentation
- The protocol transport logs every phase of frame handling—read loop wakeups, frame lengths, serialization choices, and message IDs—using structured debug logging so trace collection can replay ordering issues when needed (`src/protocol/transport.py:47`, `src/protocol/transport.py:225`).
- The rate limiter exposes optional metrics (`enable_metrics=True`) that count acquires, waits, accumulated wait time, and wakeups, which downstream diagnostics can sample to prove throttling is behaving as expected (`src/protocol/framing.py:185`, `src/protocol/framing.py:200`).

### Bridge breadcrumbs
- The Resonate bridge tracks a local pending high-water mark alongside the live pending map and exposes it via `pending_high_water_mark()`; the value is not yet surfaced to session or pool summaries, but it lets integration code audit saturation manually (`src/integration/resonate_bridge.py:56`, `src/integration/resonate_bridge.py:243`).

### Checkpoint metadata
- Checkpoints return a metadata-only snapshot (namespace size, function/class counts, import count, serialized size, and caller-provided metadata), giving operators a way to reason about namespace growth without loading objects (`src/subprocess/checkpoint.py:162`).

### Current consumers
- Beyond manual inspection, the primary consumers are regression tests that assert metrics move under cancellation, warmup, and health scenarios. No production dashboards exist yet, underscoring the need for OBS-010/011 to formalize APIs and exporters (`tests/features/test_event_driven.py:102`, `tests/features/test_warmup.py:323`, `tests/features/test_health_check.py:336`).

## Logging Guidelines
- The worker configures `structlog` to emit to stderr with a filtering bound logger so stdout remains pump-controlled and the parent can parse logs deterministically (`src/subprocess/worker.py:39`). Other modules call `structlog.get_logger()` and log key-value pairs (session IDs, execution IDs, timings) instead of free-form strings; lean on that style whenever adding diagnostics.
- Prefer warn-once mechanics for noisy conditions: the async executor’s `warn_on_blocking` gate and the threaded executor’s drain-timeout suppression both illustrate how to avoid flooding logs while still surfacing actionable context (`src/subprocess/async_executor.py:582`, `src/subprocess/executor.py:802`).
- Redirection of stdout/stderr happens inside the executor; direct `print()` or raw file writes bypass ordering guarantees and should be avoided in durable layers to keep observability consistent with pump-only outputs.

## Planned Introspection APIs
- OBS-011 (#41) will introduce guarded diagnostics APIs for pending promises, namespace summaries, and pool status. The plan adds bridge helpers that include enqueue age/timeouts, new protocol messages for namespace summaries, and policy gates with audit logging so production deployments can enable redacted, metadata-only views when appropriate.
- BRIDGE-010 (#35) complements that work by giving the Resonate bridge a lifecycle, structured shutdown rejections, and surfaced metrics (`bridge_pending_current`, `_hwm`, timeout and cancel counters) via `Session.info()` and pool summaries. Treat today’s `_pending_hwm` as a stopgap until those metrics are wired through the supported surfaces.

## Distributed Tracing
- OBS-010 (#40) defines a distributed trace buffer per session with structured `TraceEvent`s keyed by execution ID. Sessions, workers, the bridge, and future providers will emit metadata-only events (submit, pump flush, promise resolution, cancel/interrupt, etc.) either directly or via a lightweight `TraceEventMessage`. The API is slated to live under `caps.diagnostics.get_trace(...)` with bounded retention, configurable redaction, and optional exporter hooks. Until then, the transport and executor logs remain the primary way to correlate events across layers.

## Security & Redaction
- Existing telemetry surfaces expose counts, durations, and resource usage only; they never ship live objects or raw payloads across process boundaries. That aligns with the observability guidance that mandates metadata-only introspection and bounded memory (`docs/_legacy/PROCESS/ISSUE_CONVENTIONS.md:155`).
- Nevertheless, nothing in the current codebase automatically redacts sensitive identifiers from logs or metrics; authors must be deliberate about field selection. OBS-011’s policy layer will add gating and hashing for namespace and bridge identifiers, and OBS-010’s trace format bakes in truncation limits so traces stay metadata-only even when future providers join the pipeline.

## Source References
- `src/subprocess/worker.py:245`
- `src/protocol/messages.py:126`
- `src/session/manager.py:45`
- `src/session/manager.py:353`
- `src/session/manager.py:450`
- `src/session/manager.py:262`
- `src/session/pool.py:668`
- `src/session/pool.py:705`
- `src/session/pool.py:548`
- `src/session/pool.py:565`
- `src/subprocess/executor.py:301`
- `src/subprocess/executor.py:509`
- `src/subprocess/executor.py:802`
- `src/subprocess/async_executor.py:311`
- `src/subprocess/async_executor.py:580`
- `src/subprocess/async_executor.py:801`
- `src/subprocess/async_executor.py:1649`
- `src/protocol/transport.py:47`
- `src/protocol/transport.py:225`
- `src/protocol/framing.py:185`
- `src/protocol/framing.py:200`
- `src/integration/resonate_bridge.py:56`
- `src/integration/resonate_bridge.py:243`
- `src/subprocess/checkpoint.py:162`
- `tests/features/test_event_driven.py:102`
- `tests/features/test_warmup.py:323`
- `tests/features/test_health_check.py:336`
- `tests/unit/test_async_executor_cancellation.py:25`

## Legacy Material to Supersede
- The Resonate observability blueprint under `docs/_legacy/async_capability_prompts/current/21_spec_resonate_integration.md` mixes real APIs with aspirational metrics/tracing hooks; treat it strictly as background until OBS-010/011 land, and migrate any actionable guidance into this document as those features ship.
- `docs/_legacy/PROCESS/ISSUE_CONVENTIONS.md` still documents the observability checklist (bounded memory, metadata-only introspection, no additional transport readers). This guide supersedes it for the concrete surfaces that exist today but the principles remain valid.

## Open Tasks
- OBS-010 (#40): deliver the trace buffer, taxonomy, and exporter hooks so operators can reconstruct execution lifecycles without spelunking logs.
- OBS-011 (#41): wire policy-gated introspection APIs for pending promises, namespace summaries, and pool status, including the redaction controls described above.
- BRIDGE-010 (#35): expose bridge lifecycle metrics through `Session.info()`/pool summaries and make close/cancel lifecycle events observable for tracing.
