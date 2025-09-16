# Architecture Overview

> Status: Authoritative reference for Capsule runtime composition (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if code has drifted, double-check the current sources on your working commit, capture differences that affect your task, and raise any doc gaps to the user while you proceed with up-to-date information).

## Purpose & Scope
Capsule executes Python code inside managed subprocess sessions while coordinating transports, durability hooks, and diagnostics. This guide connects the cross-cutting pieces—sessions, executors, transport, integration bridge, and pooling—and explains how they cooperate today. Subsystem guides (e.g., `execution-engine.md`, `session-runtime.md`, `protocol.md`) own deeper API and implementation details; this document summarizes their interactions and points to the relevant sources.

## Component Map
Capsule’s runtime can be viewed as four layers wired together at session start:

- **Session runtime** owns the child process, routes protocol messages, and provides cancellation semantics (`Session` in `src/session/manager.py:60`).
- **Execution engine** runs user code in the worker subprocess via the threaded executor, namespace manager, and output pump (`ThreadedExecutor` in `src/subprocess/executor.py:239`, `SubprocessWorker` in `src/subprocess/worker.py:93`, `NamespaceManager` in `src/subprocess/namespace.py:16`).
- **Protocol transport** frames and ships messages over pipes between parent and child (`PipeTransport` and `MessageTransport` in `src/protocol/transport.py:120` and `src/protocol/transport.py:57`).
- **Integration bridge** optionally correlates protocol traffic with Resonate durable promises (`ResonateProtocolBridge` in `src/integration/resonate_bridge.py:24`, wired via `initialize_resonate_local` in `src/integration/resonate_init.py:32`).

An ASCII sketch of the steady-state data path:
```
Client ↔ Session (manager, queues, cancel events)
        │  ↑ heartbeat / ready
        │  ↓ execute / cancel / interrupt
PipeTransport (msgpack framing)
        │
  Worker process
        ├─ SubprocessWorker (message loop, drain policy)
        ├─ ThreadedExecutor (thread, pump, input shim)
        └─ NamespaceManager (merge-only globals)
        │
   Optional Resonate bridge (promises, capabilities)
```
`SessionPool` maintains a fleet of pre-warmed sessions for fast acquisition where required (`src/session/pool.py:82`).

## Execution Lifecycle
1. **Session creation & warmup** – The manager spawns the worker subprocess, builds a `PipeTransport`, and waits for a ready handshake before flipping to `READY` (`src/session/manager.py:123`). Optional warmup code runs through the normal execute path without exposing its output (`src/session/manager.py:174`).
2. **Receive loop & routing** – A single `_receive_loop` task reads framed messages, invokes passive interceptors, updates heartbeat metadata, and dispatches everything else onto per-execution or general queues (`src/session/manager.py:195`).
3. **Execution dispatch** – `Session.execute` serializes submissions under an internal lock, stamps `BUSY`, allocates an execution-specific queue, and streams every message (outputs, inputs, result, errors) through `_wait_for_message_cancellable`, which races the queue against the cancellation event without polling (`src/session/manager.py:375`).
4. **Worker orchestration** – `SubprocessWorker.execute` sets up `ThreadedExecutor`, starts the event-driven pump, launches a thread to run `execute_code`, and blocks on completion while draining outputs before sending a `ResultMessage` (`src/subprocess/worker.py:252`).
5. **Output pump & backpressure** – The threaded executor redirects `sys.stdout`/`sys.stderr` to `ThreadSafeOutput`, funnels chunks through an `asyncio.Queue`, and drains them via `_send_output` before acknowledging a flush sentinel (`src/subprocess/executor.py:101`; pump loop in `src/subprocess/executor.py:452`).
6. **Input & HITL** – `ThreadedExecutor.create_protocol_input` issues `InputMessage`s and blocks the worker thread until the session routes an `InputResponseMessage` back (`src/subprocess/executor.py:308`); the optional Resonate bridge correlates input promises for HITL workflows (`src/integration/resonate_bridge.py:76`).
7. **Cancellation & interrupts** – `Session.cancel` emits a `CancelMessage`, waits for cooperative shutdown, and reports success/failure; `Session.interrupt` can hard-stop and optionally restart the worker (`src/session/manager.py:495`). The worker relays cancellation into the executor’s cancel token and respects the configured grace window (`src/subprocess/worker.py:118`).
8. **Shutdown & restart** – Graceful shutdown sends a `ShutdownMessage`, waits for exit, and ultimately tears down transport and process; terminate cancels receive/routing tasks and kills the process if needed (`src/session/manager.py:606`). `SessionPool` recycles or removes unhealthy sessions and enforces idle watermarks via event-driven warmup and health-check workers (`src/session/pool.py:187`, `src/session/pool.py:358`).

## Critical Invariants
- **Single-reader transport** – Only the session receive loop reads the worker pipe; interceptors are passive, and routing fans out through asyncio queues (`src/session/manager.py:195`).
- **Pump-only outputs** – Worker code never writes to stdout/stderr directly; the threaded executor controls all output through the pump to maintain ordering and backpressure (`src/subprocess/executor.py:101`).
- **Output-before-result** – `SubprocessWorker.execute` drains the pump with a timeout and, on failure, emits an `ErrorMessage` instead of a result, preserving deterministic ordering (`src/subprocess/worker.py:314`).
- **Merge-only namespace** – The worker initializes engine internals and updates globals in place rather than replacing the namespace dictionary, preventing accidental loss of execution state (`src/subprocess/worker.py:102`; merge logic in `src/subprocess/namespace.py:68`).
- **Event loop ownership** – The parent process owns the asyncio loop; worker threads call back via `call_soon_threadsafe`, and no durable layer spins new loops (`src/subprocess/executor.py:308`).
- **Event-driven waits** – Both session message waits and pool warmup/health-check routines use events or conditions instead of polling (`src/session/manager.py:309`; `src/session/pool.py:358`).
- **Metrics surfaces** – Session and pool expose lightweight metrics (cancel triggers, pool hit/miss counters, warmup efficiency) for observability without breaking invariants (`src/session/manager.py:93`; `src/session/pool.py:568`).

Current gaps: Frame buffering on the transport side still uses a polling buffer that PROTO-010 targets for conversion to conditions, and executor drain configuration is hard-coded pending EW-012.

## Future Extensions (Planned Work)
- **Execution Engine (EW track)** –
  - Route async-friendly code paths through `AsyncExecutor` with feature gating to maintain pump/order guarantees (EW-010, #51).
  - Make drain timeout suppression configurable in the async wrapper and plumb executor knobs from `SessionConfig` into the worker (EW-011/#48, EW-012/#49).
  - Harden async cancellation handshakes and add code-object caching to reduce compile overhead (EW-013/#46, EW-014/#47).
  - Introduce structured display and progress channels that reuse the pump and session routing without violating invariants (EW-015/#27, EW-016/#28).
- **Protocol & Transport (PROTO track)** –
  - Replace the remaining FrameBuffer polling with an event-driven condition (PROTO-010/#39).
  - Add protocol negotiation and fast acknowledgements, followed by idempotency keys and durable streaming channels that extend message schemas (PROTO-011/#36, PROTO-012/#37, PROTO-013/#31).
- **Bridge & Capabilities (BRIDGE/CAP)** –
  - Surface bridge lifecycle and metrics, then prioritize control routing and interceptor quarantine to protect cancel latency (BRIDGE-010/#35, BRIDGE-011/#38).
  - Harden input EOF semantics alongside the capability registry work (CAP-011/#52, CAP-010/#30).
- **Pooling & Diagnostics (POOL/OBS)** –
  - Finish pool circuit breaker and warmup hardening (POOL-010/#29, POOL-011/#50).
  - Deliver distributed execution trace and introspection APIs with redaction policies (OBS-010/#40, OBS-011/#41).

Each item above is planned or in flight; none of the described features ship today unless noted otherwise.

## Source References
- `src/session/manager.py:60`
- `src/session/pool.py:82`
- `src/subprocess/worker.py:93`
- `src/subprocess/executor.py:239`
- `src/subprocess/namespace.py:16`
- `src/protocol/messages.py:15`
- `src/protocol/transport.py:57`
- `src/protocol/transport.py:120`
- `src/integration/resonate_bridge.py:24`
- `src/integration/resonate_init.py:32`

## Legacy Material to Supersede
The event-driven patterns and session-pool architecture documents under `docs/_legacy/architecture/` describe earlier iterations of the cancellation and warmup loops. They remain useful as historical context but no longer reflect the current code paths; consult this guide or the subsystem references instead, and copy any still-relevant nuance into the new guides when you discover it.
