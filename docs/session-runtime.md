# Session Runtime

> Status: Authoritative reference for `Session` lifecycle and routing (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if code has drifted, double-check the current sources on your working commit, capture differences that affect your task, and raise any doc gaps to the user while you proceed with up-to-date information).

## Purpose
The session runtime owns the parent side of each worker subprocess: it spawns `src.subprocess.worker`, establishes a `PipeTransport`, routes protocol messages, and exposes cancellation surfaces that other components (e.g., `SessionPool`) consume (`src/session/manager.py:60`, `src/protocol/transport.py:279`, `src/session/pool.py:306`). It is responsible for handshake and warmup, queueing semantics for execution traffic, and maintaining `Session.info` so pool orchestration and diagnostics can reason about load.

## Lifecycle
- `CREATING` is the constructor default. `start()` refuses to run unless the session is still creating, preventing double-starts (`src/session/manager.py:63-170`).
- `WARMING` marks the window after the subprocess launches but before the ready handshake arrives. The receive task waits up to 10 s for `_ready_event` before failing the session (`src/session/manager.py:148-160`).
- `READY` indicates the worker acknowledged startup. Executions may only begin in this state, and they return here after completion (`src/session/manager.py:160`, `src/session/manager.py:464-467`).
- `BUSY` wraps the execution window and is set under the session lock while `execute()` is streaming results (`src/session/manager.py:401-405`).
- `IDLE` is defined for upcoming pool/reporting work but is not yet emitted by the runtime today (`src/session/manager.py:35-42`).
- `ERROR` denotes startup failures or other fatal errors encountered while creating the worker (`src/session/manager.py:168-171`).
- `SHUTTING_DOWN` records a graceful shutdown in progress after `shutdown()` is invoked (`src/session/manager.py:606-632`).
- `TERMINATED` is the terminal state once the transport and process are torn down (`src/session/manager.py:654-690`).

`start()` forks the worker via `asyncio.create_subprocess_exec`, resets the session cancel event, constructs a `PipeTransport`, and launches the `_receive_loop` before awaiting readiness (`src/session/manager.py:123-160`). Optional warmup code runs through the same execute pipeline after the handshake, consuming all messages silently so steady-state output semantics are unchanged (`src/session/manager.py:174-193`). `shutdown()` sets the cancel event, sends a `ShutdownMessage`, and waits up to five seconds for the subprocess to exit before delegating to `terminate()` for cleanup; `terminate()` in turn cancels the receive and routing tasks, closes the transport, and kills the process if it is still alive (`src/session/manager.py:606-703`). `restart()` simply calls `terminate()`, clears `_ready_event`, and re-enters the startup path (`src/session/manager.py:692-704`). `is_alive` treats a running process as healthy only when the state is neither terminal nor `CREATING`, which keeps pool logic from reusing sessions that are mid-shutdown (`src/session/manager.py:111-121`).

## Receive Loop & Routing
The `start()` handshake schedules `_receive_loop()` on the session event loop so Capsule upholds the single-reader invariant—no other coroutine touches the worker transport (`src/session/manager.py:148-199`). `_receive_loop()` issues non-blocking reads with a 100 ms timeout, invokes any registered interceptors sequentially, logs (but suppresses) interceptor errors, and handles two message families inline: a `ReadyMessage` flips `_ready_event`, while `HeartbeatMessage`s refresh memory and CPU telemetry on `Session.info` (`src/session/manager.py:201-240`). All other traffic is dispatched by creating routing tasks that push messages onto execution-specific queues (keyed as `execution:<id>`) or a shared `general` queue for control and capability responses without an `execution_id` (`src/session/manager.py:242-291`). Routing tasks are tracked in `_routing_tasks` so `terminate()` can cancel and await them before closing the transport (`src/session/manager.py:244-257`, `src/session/manager.py:668-675`).

Interceptors can be registered and removed via `add_message_interceptor()` / `remove_message_interceptor()`; they run on the receive loop thread and must remain non-blocking to avoid delaying routing (`src/session/manager.py:293-307`). Consumers that need to await ad-hoc responses use `receive_message()`, which lazily creates the general queue and reuses the same cancellable wait primitive described below to honor timeouts and cancellation without spinning (`src/session/manager.py:561-604`).

## Execution API
`execute()` is an async generator that streams every message correlated with a submitted `ExecuteMessage` (`src/session/manager.py:375-458`):

1. Guard rails reject calls while the session is creating, shutting down, terminated, or has previously errored, and the transport must exist (`src/session/manager.py:389-400`).
2. Under the internal lock the state flips to `BUSY`, `last_used_at` is updated, and `execution_count` increments so pool telemetry stays accurate (`src/session/manager.py:401-405`).
3. A dedicated `asyncio.Queue` is registered for the execution id before the `ExecuteMessage` is sent across the transport (`src/session/manager.py:406-414`).
4. The generator loops until a `ResultMessage` or `ErrorMessage` is observed. Each iteration derives an absolute deadline (if provided) and awaits `_wait_for_message_cancellable(queue, remaining)` so the session can respond immediately when cancellation is signaled (`src/session/manager.py:418-444`).
5. Messages whose `execution_id` matches the active request are yielded in order. Input prompts keep the loop running, while results increment `error_count` on failures and end the generator (`src/session/manager.py:433-440`).
6. `TimeoutError` propagates if the deadline expires, and `asyncio.CancelledError` surfaces if `_cancel_event` fires; when metrics are enabled the latter increments `executions_cancelled` for observability (`src/session/manager.py:445-456`).
7. Finally, the per-execution queue is removed and the session returns to `READY` inside the lock (`src/session/manager.py:459-467`).

`_wait_for_message_cancellable()` is the core event-driven primitive shared by execution and general receive paths. It races `queue.get()` with the session-wide cancel event using `asyncio.wait(return_when=FIRST_COMPLETED)` and monotonic deadlines, cleans up both tasks deterministically, and increments the `cancel_event_triggers` metric when cancellation wins (`src/session/manager.py:309-373`). `input_response()` packages user input into an `InputResponseMessage` and is used by bridge/HITL layers when fulfilling prompts (`src/session/manager.py:480-493`).

## Cancellation & Interrupts
Session-level cancellation has two layers:

- Cooperative cancellation sets `_cancel_event`, which unwinds any blocked waits (`start()` resets it; `shutdown()` and `terminate()` set it before cleaning up) and keeps `execute()` responsive even when no transport traffic arrives (`src/session/manager.py:130-132`, `src/session/manager.py:616-617`, `src/session/manager.py:656-658`).
- Protocol cancellation emits control messages. `cancel()` sends a `CancelMessage` with a configurable grace window, polls worker liveness in 10 ms slices, and returns `False` if the subprocess dies (signalling the caller to recycle the session); otherwise it reports `True` after the grace window elapses (`src/session/manager.py:495-531`). `interrupt()` issues an `InterruptMessage` and, when `force_restart=True`, waits briefly before restarting the session if the worker exited (`src/session/manager.py:533-560`).

Both paths rely on the worker honoring cancel/interrupt semantics by cancelling the active executor and respecting the output-before-result invariant, which is enforced on the worker side (`src/subprocess/worker.py:221-344`). Because the runtime does not yet receive acknowledgements, callers should treat `cancel()`/`interrupt()` as best-effort signals; planned protocol negotiation work will tighten this contract (see below).

## Error Handling & Metrics
`Session.info` exposes a snapshot dataclass that mirrors the latest state, timestamps, execution/error counters, and the most recent heartbeat telemetry (`src/session/manager.py:45-103`, `src/session/manager.py:238-240`). The receive loop keeps this metadata fresh while `execute()` updates counters synchronously. Startup failures flip the state to `ERROR` before bubbling the exception so pool orchestrators can react (`src/session/manager.py:168-171`). Graceful shutdown and termination paths log structured errors, cancel routing tasks, and close the transport before force-killing the subprocess as a last resort (`src/session/manager.py:606-690`). Lightweight metrics for cancel-event triggers and cancelled executions are maintained in `_metrics` and only increment when `SessionConfig.enable_metrics` is set (`src/session/manager.py:93-97`, `src/session/manager.py:353-366`, `src/session/manager.py:450-452`). `SessionConfig` currently exposes toggles for metrics and baseline timeouts; future work will expand these knobs (see EW-012 below) (`src/session/config.py:1-18`).

## Planned Enhancements
- **Protocol negotiation & acknowledgements (#36 / PROTO-011)** – `start()` will send a new `HelloMessage`, record negotiated protocol capabilities on `Session.info.metadata`, and `_route_message()` will map `AckMessage`s so `execute()` can surface early acceptance without violating single-reader or output-before-result invariants.
- **Priority routing & interceptor quarantine (#38 / BRIDGE-011)** – `_receive_loop()` will classify control vs bulk traffic, introduce weighted dispatch to guarantee sub-50 ms cancel latency, and measure interceptor runtimes so chronic offenders can be quarantined without blocking routing.
- **Executor/worker configuration plumbing (#49 / EW-012)** – `SessionConfig` will grow executor and pump configuration; `start()` will pass overrides via the worker environment so `SubprocessWorker` can honor custom timeouts and backpressure policies while keeping drain semantics unchanged.
- **Diagnostics and namespace introspection (#41 / OBS-011)** – The runtime will add request/response pairs for namespace summaries and surface queue/priority telemetry on `Session.info`, enabling guarded diagnostics APIs that expose metadata without leaking user data.
- **Input EOF/timeout semantics for HITL (#52 / CAP-011)** – Once the bridge lifecycle closes pending promises deterministically, session shutdown hooks will propagate EOF semantics promptly so capability callers see `EOFError`/`TimeoutError` rather than opaque promise failures.
- **Per-execution input response routing (FUTURE #4)** – The worker currently routes input responses to the active executor; future work will key executors by execution id, tightening coupling between session routing and worker input handling in preparation for concurrency experiments.

These items are not yet shipped; until they land, the behaviors described in the sections above remain the single source of truth.

## Source References
- `src/session/manager.py:32`
- `src/session/manager.py:60`
- `src/session/manager.py:123`
- `src/session/manager.py:195`
- `src/session/manager.py:309`
- `src/session/manager.py:375`
- `src/session/manager.py:495`
- `src/session/manager.py:606`
- `src/session/manager.py:654`
- `src/session/config.py:1`
- `src/protocol/transport.py:279`
- `src/subprocess/worker.py:221`
- `src/session/pool.py:306`

## Legacy Material to Supersede
The “Session Manager Event-Driven Cancellation” pattern in `docs/_legacy/architecture/event_driven_patterns.md` describes an earlier version of `_wait_for_message_cancellable()`. This guide now documents the actual implementation and should be treated as the authoritative reference; consult the legacy doc only for historical context, and migrate any missing details here if you spot gaps.
