# Capsule

> Development Status: 🚧 Experimental (v0.1.0‑dev) — Phase 3 in progress

Capsule is a Python Subprocess‑Isolated Execution Service (SIES). It provides persistent subprocess sessions, a framed async transport for streaming I/O, and durable request correlation to power interactive execution patterns.

## Current Capabilities

### Protocol & Transport
- Messages: Execute, Output, Input, InputResponse, Result, Error, Checkpoint, Restore, Ready, Heartbeat, Shutdown, Cancel, Interrupt.
- Framed transport over stdin/stdout with MessagePack or JSON encoding.
- Event‑driven FrameReader (asyncio.Condition). FrameBuffer still uses a small polling loop and is planned to move to Condition.

### Session
- Lifecycle: start, shutdown, terminate, restart; `is_alive`; `Session.info()` updated via heartbeats.
- Execution: `Session.execute(msg)` yields Output/Result/Error as an async generator; `input_response()` replies to Input; `cancel()`/`interrupt()` supported.
- Routing: passive message interceptors (non‑blocking); single‑reader invariant (Session is the only transport reader); event‑driven receive loop with cancellable waits.

### Worker
- Executes code via ThreadedExecutor today. Enforces strict output‑before‑result ordering by draining the event‑driven output pump.
- If drain times out, emits an ErrorMessage and never a ResultMessage (preserves ordering).
- Heartbeats (memory/CPU/namespace), Checkpoint/Restore (local mode), busy guard, cancel with grace timeout (escalates to restart if needed), and interrupt handling.

### Executors
- ThreadedExecutor (production path):
  - Blocking‑safe via thread execution. Protocol `input()` shim (sends InputMessage, blocks for InputResponse).
  - Event‑driven output pump (asyncio.Queue, flush sentinel), backpressure modes (block, drop_new, drop_oldest, error), cooperative cancellation via `sys.settrace`.
  - Captures trailing expression value after exec blocks for REPL UX.
  - Async wrapper `execute_code_async()` is test‑only — it suppresses drain timeout warnings; the worker remains strict.
- AsyncExecutor (native paths implemented; worker routing pending):
  - Compile‑first top‑level await using `PyCF_ALLOW_TOP_LEVEL_AWAIT`, then exec+flags; minimal AST wrapper fallback as last resort.
  - Executes simple sync and async‑def defining code natively; optional flag‑gated transforms are default‑off.
  - Bounded AST LRU and fallback linecache LRU; coroutine tracking and `cancel_current()` with counters and cleanup.
  - Heuristics for BLOCKING_SYNC detection with overshadow/import guards reduce false positives. Used via DI/tests; worker routing is planned behind a flag.

### Namespace
- Merge‑only namespace policy; preserves `ENGINE_INTERNALS` (In/Out history, result slots `_`, `__`, `___`); never replaces the namespace dict.
- Snapshots (create/restore/delete), serialization helpers, tracked function/class sources and imports.

### Session Pool
- Event‑driven warmup (signals, no polling) with watermark checks.
- Hybrid health check worker (timer baseline + event triggers).
- Pool metrics and `get_info()` (hit rate, warmup/health metrics, acquisition latency, etc.).

### Integration
- ResonateProtocolBridge (local mode): durable promises for Execute/Input flows, structured timeout rejection, pending high‑water mark.
- DI wiring for AsyncExecutor and a HITL Input capability. Lifecycle/metrics surfacing via `Session.info()` planned.

## Design Invariants
- Single‑reader transport: Session is the only transport reader.
- Output‑before‑result: Worker drains output pump before Result; timeout → Error (no Result).
- Merge‑only namespace: Never replace dict; preserve `ENGINE_INTERNALS` keys.
- Pump‑only outputs: stdout/stderr routed through the async output pump.
- Event‑driven I/O: Prefer Conditions/Events over polling (FrameBuffer refactor pending).

## Architecture Overview

```
Protocol Layer
├── Framed transport (MessagePack/JSON)
├── Event‑driven FrameReader (asyncio.Condition)
└── Message schemas (messages.py)

Execution Layer
├── ThreadedExecutor (blocking‑safe, pump/backpressure, input shim)
├── AsyncExecutor (TLA compile‑first; async‑def/simple sync native; AST fallback; caches; cancel_current)
└── NamespaceManager (merge‑only; ENGINE_INTERNALS)

Integration Layer (Local)
├── ResonateProtocolBridge (durable promises)
├── DI wiring (async executor, HITL capability)
└── Session interceptors
```

## Installation

Capsule is not yet published to PyPI. To use it in development:

```bash
# Clone the repository
git clone https://github.com/your-org/capsule.git
cd capsule

# Install with uv (recommended)
uv sync

# Or with pip in development mode
pip install -e .
```

## Usage Examples

### Basic Code Execution

```python
import asyncio
from src.session.manager import Session
from src.protocol.messages import ExecuteMessage

async def main():
    session = Session()
    await session.start()
    
    # Execute simple Python code
    exec_msg = ExecuteMessage(
        id="exec-1",
        timestamp=time.time(),
        code="x = 2 + 2\nprint(f'Result: {x}')\nx"
    )
    
    async for msg in session.execute(exec_msg):
        if msg.type == "output":
            print(msg.data, end="")
        elif msg.type == "result":
            print(f"Final value: {msg.value}")
    
    await session.shutdown()

asyncio.run(main())
```

### Interactive Input

```python
async def interactive_example():
    session = Session()
    await session.start()
    
    exec_msg = ExecuteMessage(
        id="exec-2",
        timestamp=time.time(),
        code="name = input('Enter your name: ')\nprint(f'Hello, {name}!')"
    )
    
    async for msg in session.execute(exec_msg):
        if msg.type == "input":
            # Respond to input request
            await session.input_response(msg.input_id, "Alice")
        elif msg.type == "output":
            print(msg.data, end="")
    
    await session.shutdown()
```

### Local-Mode Promises (Experimental)

```python
from src.integration.resonate_init import initialize_resonate_local
from src.integration.resonate_bridge import ResonateProtocolBridge

async def promise_example():
    session = Session()
    await session.start()
    resonate = initialize_resonate_local(session)
    
    # Bridge handles promise correlation
    bridge = resonate.dependencies["protocol_bridge"]
    
    # Execute with promise-based result
    execution_id = "exec-3"
    promise_id = f"exec:{execution_id}"
    promise = resonate.promises.create(id=promise_id, timeout=30000, data="{}")
    
    # ... execution via bridge ...
    
    await session.shutdown()
```

## Development

```bash
# Install development dependencies
uv sync

# Run tests
uv run pytest

# Run specific test categories
uv run pytest -m unit          # Fast unit tests
uv run pytest -m integration   # Integration tests

# Type checking
uv run mypy src/
uv run basedpyright src/

# Linting & Formatting (configured in pyproject.toml)
uv run ruff check src/
uv run ruff format src/

# Test with coverage
uv run pytest --cov=src --cov-report=term-missing
```

## Project Structure

```
capsule/
├── src/
│   ├── subprocess/       # Executors and namespace management
│   │   ├── executor.py   # ThreadedExecutor (working)
│   │   ├── async_executor.py # AsyncExecutor (native paths; worker routing pending)
│   │   └── namespace.py  # Namespace management
│   ├── session/          # Session and pool management
│   ├── protocol/         # Message protocol and transport
│   └── integration/      # Resonate SDK integration
├── tests/
│   ├── unit/            # Component tests
│   └── integration/     # Cross-component tests
└── docs/
    ├── planning/        # Phase documentation
    └── development/     # Implementation notes
```

## Roadmap Highlights

Workstreams (see milestones/issues):
- Executor & Worker (EW): SessionConfig plumbing; AsyncExecutor lifecycle finalize; drain suppression knob; worker native async route (flagged); Display/Progress messages.
- Protocol & Transport (PROTO): Event‑driven FrameBuffer; Hello/Ack negotiation; idempotency keys; durable streaming channels.
- Bridge & Capabilities (BRIDGE): lifecycle + metrics via `Session.info()`; priority routing & interceptor quarantine; CapabilityRegistry & SecurityPolicy; input EOF/timeout semantics.
- Session Pool (POOL): finalize warm imports and memory budgets; circuit breaker + metric safety.
- Providers (PROV): SDK/contract tests; HTTP/Files/Shell providers with allowlists and caps.
- Observability (OBS): distributed execution trace; safe introspection (redacted metadata).

See `ROADMAP.md` for details.

## Contributing

We welcome contributions! Please read the guidelines and use our issue templates to keep work scoped and reviewable.

- Contributing Guide: see `CONTRIBUTING.md` (development workflow, testing, PR guidance)
- Issue Conventions (titles, labels, required sections, invariants, rollout/flags): `docs/PROCESS/ISSUE_CONVENTIONS.md`
- GitHub Issue Templates: `.github/ISSUE_TEMPLATE/`


### Focus Areas

Capsule is in early development. Priority areas for contributions:

- Phase 3: Worker native AsyncExecutor routing (flagged)
- Capability system development
- Test coverage improvement
- Documentation
- Performance optimization

See [FOUNDATION_FIX_PLAN.md](FOUNDATION_FIX_PLAN.md) for detailed development status.

## License

MIT
