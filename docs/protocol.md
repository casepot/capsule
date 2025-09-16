# Protocol & Transport

> Status: Authoritative reference for Capsule protocol and transport (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if code has drifted, double-check the current sources on your working commit, capture differences that affect your task, and raise any doc gaps to the user while you proceed with up-to-date information).

## Purpose
The protocol layer defines the wire format for every message exchanged between the session manager and the worker subprocess, and the transport layer guarantees delivery ordering, framing, and lifecycle management. `Session` serializes submissions, routes worker responses, and enforces cancellation semantics, while `SubprocessWorker` produces protocol messages that honor Capsule’s single-reader and output-before-result invariants (`src/session/manager.py:123`, `src/subprocess/worker.py:221`). `MessageTransport` serializes those models over the pipe using length-prefixed frames so higher layers can treat the channel as a typed message bus (`src/protocol/transport.py:198`).

## Message Schemas (Current)
All protocol models inherit `BaseMessage`, which supplies a unique `id` and `timestamp` for correlation and tracing (`src/protocol/messages.py:36`). The union `Message` enumerates every type supported today; unrecognized payloads raise `ValueError` during parsing so invalid traffic fails fast (`src/protocol/messages.py:155`, `src/protocol/messages.py:204`).

- **ExecuteMessage** — carries the Python source to run plus transaction metadata (`transaction_id`, `transaction_policy`) and an opt-in flag for source capture. The message `id` becomes the execution correlation key used by both session routing and worker telemetry (`src/protocol/messages.py:42`).
- **OutputMessage** — encapsulates stdout/stderr text chunks with an explicit `stream` (`stdout` or `stderr`) and the originating `execution_id`. Output messages are ordered and drained before any result messages leave the worker (`src/protocol/messages.py:57`, `src/subprocess/worker.py:333`).
- **InputMessage** — emitted when user code calls `input()` via the executor shim. It includes the prompt, `execution_id`, and optional timeout so the session can surface interactive prompts without polling (`src/protocol/messages.py:64`, `src/subprocess/executor.py:308`).
- **InputResponseMessage** — sent by the session when a client responds to an input prompt; it references the original prompt via `input_id` and never carries an `execution_id` because prompts can outlive the execution identifier on retries (`src/protocol/messages.py:71`, `src/session/manager.py:493`).
- **ResultMessage** — reports successful completion. `value` is only populated when the result is JSON-serializable; otherwise clients rely on the textual `repr`. `execution_time` captures wall-clock duration for observability (`src/protocol/messages.py:77`, `src/subprocess/worker.py:386`).
- **ErrorMessage** — transports structured exceptions. When the error originates inside a user execution, `execution_id` is populated; worker- or transport-level failures leave it `None`. The traceback string mirrors what was printed to stderr, preserving ordering guarantees (`src/protocol/messages.py:85`, `src/subprocess/worker.py:349`).
- **CheckpointMessage** — optional durability hook that can announce checkpoints or carry serialized namespace blobs. The bytes payload survives round-trips because msgpack serialization preserves binary data (`src/protocol/messages.py:95`, `src/protocol/transport.py:215`).
- **RestoreMessage** — instructs the worker to restore prior state, either by checkpoint identifier or inline bytes. `clear_existing=True` (the default) wipes the namespace before replay (`src/protocol/messages.py:108`).
- **ReadyMessage** — emitted once per worker startup, advertising the session identifier and the currently enabled capabilities (`src/protocol/messages.py:118`, `src/subprocess/worker.py:221`). `Session.start` waits on this message before declaring the session ready (`src/session/manager.py:151`).
- **HeartbeatMessage** — sent every five seconds while the worker is healthy, reporting RSS, CPU percent, and namespace size so the parent can expose lightweight telemetry (`src/protocol/messages.py:126`, `src/subprocess/worker.py:245`).
- **ShutdownMessage** — cooperatively shuts down the worker, optionally requesting a checkpoint before exit. Sessions emit it during graceful teardown and expect the worker to close the pipe voluntarily (`src/protocol/messages.py:133`, `src/session/manager.py:632`).
- **CancelMessage** — carries an `execution_id` and grace-period hint (default 500 ms) so the worker can attempt a soft cancellation before the session escalates (`src/protocol/messages.py:141`, `src/session/manager.py:512`).
- **InterruptMessage** — the hard-stop control message that can optionally force a worker restart after interruption (`src/protocol/messages.py:149`, `src/session/manager.py:548`).

Example payloads demonstrate both serialization modes. The msgpack frame written on the wire for an output chunk begins with a four-byte big-endian length prefix followed by the binary msgpack blob created from `message.model_dump(mode="python")`. When the optional JSON fallback is used, the same message surfaces as:

```json
{
  "type": "output",
  "id": "01HXYKF9E9ST8ZP9S4W6K5JQ0K",
  "timestamp": 1716429476.224113,
  "data": "print done\n",
  "stream": "stdout",
  "execution_id": "01HXYKF9E9ST8ZP9S4W6K5JQ0K"
}
```

## Framing & Transport
The pipe protocol is length-prefixed: each frame starts with a four-byte big-endian payload size followed by the serialized message bytes. `FrameReader` runs as a background task that reads from the subprocess pipe, buffers bytes, and wakes waiting consumers via an `asyncio.Condition`. It enforces the 10 MB frame ceiling and raises `ProtocolError` if the connection closes mid-frame or an oversized payload arrives (`src/protocol/transport.py:45`, `src/protocol/transport.py:113`). `FrameWriter` serializes frames under a write lock to respect backpressure (`src/protocol/transport.py:170`).

`MessageTransport` wraps both reader and writer, choosing msgpack by default so binary payloads such as checkpoints can round-trip without base64 inflation; a JSON fallback exists for tooling that cannot parse msgpack (`src/protocol/transport.py:198`). Deserialized dictionaries flow through `parse_message`, yielding typed Pydantic models that downstream components can inspect without revalidating schema (`src/protocol/transport.py:254`). `PipeTransport` binds this stack to an `asyncio.create_subprocess_exec` process object and, on close, terminates or kills the child if it does not exit within five seconds (`src/protocol/transport.py:282`, `src/protocol/transport.py:309`).

`FrameBuffer` lives alongside the transport to collect raw frames; it accepts append calls under an `asyncio.Lock`, validates the same 10 MB bound, and exposes `get_frame(timeout)` for polling consumers (`src/protocol/framing.py:12`). Today it still relies on a 10 ms sleep while waiting for new data, a known gap tracked by PROTO-010 (`src/protocol/framing.py:71`). `StreamMultiplexer` and `RateLimiter` are support primitives for upcoming streaming and throttled message paths: the multiplexer maintains per-stream queues without breaking the single-reader invariant, and the rate limiter computes precise wait intervals rather than polling (`src/protocol/framing.py:97`, `src/protocol/framing.py:155`).

## Ordering & Invariants
- **Single reader** — Only `Session._receive_loop` touches the transport, reading with a 100 ms timeout and handing every other concern off to routing tasks. Interceptors run inline on that same loop but must remain passive to protect ordering (`src/session/manager.py:195`).
- **Ready-before-work** — Session startup waits for the worker’s `ReadyMessage` before transitioning to `READY`; the worker emits the message once it has initialized namespace internals and enumerated capabilities (`src/session/manager.py:151`, `src/subprocess/worker.py:221`).
- **Execution routing** — Messages carrying an `execution_id` flow into per-execution queues keyed by the execute message id; everything else lands on a shared general queue for control and capability responses (`src/session/manager.py:280`). `Session.execute` consumes from the relevant queue using an event-driven wait that races message arrival against cancellation without chunked polling (`src/session/manager.py:309`).
- **Output-before-result** — The worker drains the executor’s pump and enforces a hard timeout; on failure it emits an `ErrorMessage` and withholds the result to preserve deterministic ordering for clients listening to stdout, stderr, and result streams (`src/subprocess/worker.py:333`).
- **Interactive input** — Input messages originate on the worker thread but are delivered asynchronously via the pump and resolved through `Session.input_response`, preserving the thread-safe coordination between executor and session (`src/subprocess/executor.py:308`, `src/session/manager.py:493`).
- **Heartbeat cadence** — The worker sends telemetry every five seconds while `_running` is true. Session updates `SessionInfo` in place, enabling pooling and diagnostics surfaces to query current memory and CPU data without additional RPCs (`src/subprocess/worker.py:245`, `src/session/manager.py:235`).
- **Error handling** — Oversized frames or mid-frame disconnects raise `ProtocolError` or `ValueError`, and the buffer clears itself so subsequent payloads can resume on a clean state (`src/protocol/framing.py:40`, `src/protocol/transport.py:105`). Session shutdown escalates from `ShutdownMessage` to transport close, terminating or killing the subprocess if it does not cooperate within the configured grace window (`src/session/manager.py:632`, `src/protocol/transport.py:309`).

## Planned Extensions (Not Yet Shipped)
- **Event-driven FrameBuffer** — PROTO-010 ([#39](https://github.com/casepot/capsule/issues/39)) will replace the remaining 10 ms sleep with an `asyncio.Condition`, add wait/wakeup metrics, and align buffering semantics with `FrameReader`.
- **Protocol negotiation & fast acknowledgements** — PROTO-011 ([#36](https://github.com/casepot/capsule/issues/36)) introduces `HelloMessage`/`AckMessage`, publishes negotiated protocol versions via `Session.info`, and provides Ack-before-output ordering so clients see immediate acceptance signals.
- **Capability idempotency** — PROTO-012 ([#37](https://github.com/casepot/capsule/issues/37)) adds capability request/response message types with optional idempotency keys plus a bridge-side cache negotiated through the new handshake.
- **Durable streaming channels** — PROTO-013 ([#31](https://github.com/casepot/capsule/issues/31)) wires `StreamMultiplexer` into the protocol with stream open/data/close messages, bounded backpressure, and bridge coordination for async generators.
- **Structured display payloads** — EW-015 ([#27](https://github.com/casepot/capsule/issues/27)) will extend `MessageType` with `display`, route MIME bundle chunks through the existing pump, and expose helper APIs guarded by feature flags.
- **Progress updates** — EW-016 ([#28](https://github.com/casepot/capsule/issues/28)) adds `ProgressMessage`, executor-side rate limiting, and bounded per-execution queues so structured progress never blocks results.

Each effort above is in planning or implementation; unless explicitly noted in release notes, the current runtime still speaks the message set documented earlier.

## Source References
- `src/protocol/messages.py:9`
- `src/protocol/framing.py:12`
- `src/protocol/framing.py:97`
- `src/protocol/framing.py:155`
- `src/protocol/transport.py:22`
- `src/protocol/transport.py:198`
- `src/session/manager.py:123`
- `src/session/manager.py:195`
- `src/session/manager.py:280`
- `src/subprocess/worker.py:221`
- `src/subprocess/worker.py:333`
- `src/subprocess/executor.py:308`

## Legacy Material to Supersede
Historical protocol write-ups under `docs/_legacy/async_capability_prompts/current/20_spec_architecture.md` and the polling investigation in `docs/_legacy/async_capability_prompts/archive/obsolete_01_investigation_polling.md` describe earlier assumptions (no negotiation, more polling). This guide reflects the current wire format and transport behavior; consult the legacy documents only for historical context and port any still-relevant nuance into this file when gaps are discovered.

## Maintenance Checklist
- Update the message catalog whenever new `MessageType` values (e.g., negotiation, capability, display, progress) land in `src/protocol/messages.py`.
- Capture new framing or backpressure semantics—especially as PROTO-010 migrates `FrameBuffer` to an event-driven wait or future work introduces stream channels.
- Expand serialization examples and error-path coverage if we add alternative transports, compression, or handshake phases.
