# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test categories
pytest -m unit                    # Unit tests only
pytest -m integration             # Integration tests
pytest -m "not slow"             # Exclude slow tests
pytest tests/features/           # Feature tests
pytest tests/stress/             # Stress tests

# Run specific test file
pytest tests/integration/test_session.py

# Run tests in parallel (if pytest-xdist installed)
pytest -n auto
```

### Code Quality
```bash
# Type checking
mypy src/
basedpyright src/

# Linting
ruff check src/ tests/

# Formatting
black src/ tests/
```

### Development
```bash
# Install with dev dependencies
pip install -e .[dev]

# Run demo
python main.py

# Run worker directly (for debugging)
python -m src.subprocess.worker
```

## Architecture Overview

PyREPL3 is a subprocess-isolated Python execution service with 4 main layers:

### Protocol Layer (`src/protocol/`)
- **messages.py**: 13 message types (Execute, Output, Input, Result, Error, etc.) using Pydantic models
- **transport.py**: Binary framing protocol with MessagePack/JSON serialization
- **framing.py**: Output handling with backpressure management and rate limiting (event-driven)

### Session Layer (`src/session/`)
- **manager.py**: Session lifecycle (CREATING → WARMING → READY → BUSY → IDLE → TERMINATED)
- **pool.py**: Pre-warmed session pooling with event-driven warmup and health checks
- **config.py**: Configuration for timeouts, limits, and pool settings

### Subprocess Layer (`src/subprocess/`)
- **worker.py**: Main subprocess entry point, message routing, cooperative cancellation
- **executor.py**: ThreadedExecutor runs user code in threads, bridges async I/O
- **namespace.py**: Transaction support, source tracking, namespace management
- **checkpoint.py**: Dill-based serialization for state persistence

### API Layer (`src/api/`)
Currently empty - planned for WebSocket/REST endpoints

## Key Patterns and Conventions

### Event-Driven Architecture
All background operations use `asyncio.Event` - no polling loops:
```python
# Pattern used throughout
async def wait_for_condition():
    await self._event.wait()  # Blocks until event.set()
```

### Thread-Safe Async Bridge
User code runs in threads, I/O happens in async context:
```python
# Thread context writes
sys.stdout = ThreadSafeOutput(executor, StreamType.STDOUT)

# Async context pumps
async def output_pump():
    item = await output_queue.get()  # Event-driven
    await transport.send_message(OutputMessage(...))
```

### Session State Management
Sessions track state with proper transitions:
- Use `async with session._state_lock:` for state changes
- Always check `session.state` before operations
- Handle TERMINATED state gracefully

### Message Protocol
- All messages inherit from `BaseMessage` with `id` and `timestamp`
- Use `MessageType` enum for type field
- Messages are serialized with MessagePack (fallback to JSON)
- 4-byte length prefix for framing

### Testing Patterns
```python
# Use fixtures from tests/fixtures/
from tests.fixtures.sessions import create_session, SessionHelper

async def test_example():
    async with create_session() as session:
        messages = await SessionHelper.execute_code(session, "print('test')")
        assert_output_contains(messages, "test")
```

### Testing Best Practices (Learned from Failures)
1. **Default to session reuse** - Creating new Session() needs justification (isolation, specific state). New sessions cause resource exhaustion
2. **Start background tasks explicitly** - `await transport.start()`, `await pool.start()`
3. **Handle InputMessage in execute loops** - Must respond via `session.input_response()`
4. **Verify APIs exist before testing** - Many tests were written for imaginary methods
5. **Use proper AsyncMock configuration** - FrameReader has complex async architecture
6. **Check actual message types** - Messages use string literals, not just enums
7. **Allow for subprocess startup time** - Minimum 50-100ms for Python interpreter

## Critical Implementation Details

### Input Handling
The system overrides Python's `input()` function via a custom displayhook that sends INPUT messages and waits for INPUT_RESPONSE messages. This enables interactive code in subprocesses.

### Cancellation
Uses `sys.settrace()` for cooperative cancellation - checks cancellation event on each line/call. More responsive than signal-based approaches.

### Lock-Free Pool Pattern
Session pool uses placeholder reservation to avoid holding locks during subprocess creation (100-500ms operation):
```python
# Reserve slot quickly
async with self._lock:
    placeholder_id = f"creating-{uuid.uuid4()}"
    self._all_sessions[placeholder_id] = None

# Create without lock
session = await self._create_session(register=False)

# Swap atomically
async with self._lock:
    del self._all_sessions[placeholder_id]
    self._all_sessions[session.session_id] = session
```

### Output Streaming
- Backpressure policies: BUFFER, BLOCK, DROP
- Rate limiting with token bucket (event-driven refill)
- Automatic flushing on execution completion

## Future Direction

The project plans to integrate Resonate SDK for durability and orchestration (see `docs/async_capability_prompts/`), but this is not yet implemented. Current focus is on stabilizing the core execution engine and protocol.

## Common Development Tasks

### Adding a New Message Type
1. Define in `src/protocol/messages.py` with `MessageType` enum
2. Create message class inheriting from `BaseMessage`
3. Handle in `src/subprocess/worker.py` message routing
4. Add tests in `tests/unit/test_messages.py`

### Debugging Session Issues
1. Check session state transitions in logs
2. Verify transport connection with `session._transport.connected`
3. Monitor `_execution_tasks` for hanging executions
4. Use `session.get_info()` for metrics

### Debugging Hangs and Deadlocks
```python
# Common hang points and solutions:
# 1. Session warmup during start() - move outside lock
# 2. Pool acquire waiting forever - check max_sessions limit
# 3. Execute not yielding messages - check async generator consumption
# 4. Input response timeout - verify input_response() called with correct ID
```

### Performance Testing
```bash
# Run stress tests
pytest tests/stress/ -v

# Check pool metrics
pool.get_info()  # Returns hit_rate, acquisition times, etc.
```

### Performance Optimizations Applied
1. **Event-driven patterns**: Replaced 6 polling patterns with events
   - Session Manager: ~60 wakeups/min → 0 (asyncio.Event for cancellation)
   - Pool warmup: 6 wakeups/min → <0.1 (event on watermark violation)
   - Health check: 2 wakeups/min → <0.2 (hybrid with baseline timer)
   - Rate limiter: unbounded → ≤1 per acquire (exact wait calculation)

2. **Output handling**: Flush sentinels ensure ordering
   - asyncio.Queue replaces queue.Queue
   - No polling or timing heuristics needed
   - <10ms latency for output streaming

3. **Cancellation**: Two-tier system
   - Cooperative via sys.settrace (allows cleanup)
   - Hard via worker restart (guaranteed termination)
   - Check interval of 100 for ~1% overhead

## Critical Bugs Fixed (from investigation_log.json)

### High-Priority Issues Resolved
1. **Worker stdin/stdout initialization**: Must use `sys.stdin.buffer` and `sys.stdout.buffer` for binary streams
2. **AsyncIterator await bug**: Use `async for` with async generators, not `await`
3. **MessageTransport.start()**: Must be called in worker to start FrameReader._read_loop
4. **Re-entrant lock deadlock**: Never call methods that need locks while holding the same lock
5. **Double execution bug**: Detect expression vs statement upfront to avoid exec then eval
6. **Output race conditions**: Implemented event-driven queue/pump with flush sentinels
7. **Input override persistence**: Don't restore builtins.input after execution - keep protocol override
8. **Session reuse pattern**: MANDATORY - each Session() creates new subprocess with fresh namespace

### Architecture Invariants (Must Maintain)
- **Single-reader invariant**: Only one execution per session at a time
- **Thread/async separation**: User code in threads, infrastructure async
- **Event-driven only**: No polling loops anywhere (except hybrid health check baseline)
- **Lock scope discipline**: Never await expensive operations while holding locks
- **Namespace persistence**: exec() and eval() need namespace for both globals AND locals

### Common Pitfalls to Avoid
1. **Creating new Session per test**: Causes resource exhaustion (2000+ file descriptors)
   - Use session fixtures and reuse sessions
   - Each session = new subprocess = 5-10MB memory + 2 FDs

2. **Holding locks during subprocess creation**: Causes deadlock
   - Use placeholder reservation pattern
   - Lock only for state checks and updates, not I/O

3. **Using dont_inherit=True in compile()**: Breaks cooperative cancellation
   - Tracer won't propagate to exec/eval frames
   - Use dont_inherit=False for cancellable code

4. **Not starting background tasks**: Tests fail mysteriously
   - FrameReader needs await transport.start()
   - SessionPool needs await pool.start()

5. **Ignoring message correlation IDs**: Input responses get lost
   - InputMessage.id must match InputResponseMessage.input_id
   - ExecuteMessage.id correlates with ResultMessage.execution_id

6. **Assuming sync patterns in async code**: Causes race conditions
   - Use asyncio.Event for signaling
   - Use asyncio.Queue for async producer/consumer
   - call_soon_threadsafe for thread-to-async communication

## Gotchas

- Session pool warmup is event-driven, not polling - don't look for timer loops
- User code runs in threads but protocol I/O is async - careful with synchronization
- Subprocess creation takes 50-100ms minimum due to Python interpreter startup
- Always use context managers for session lifecycle to ensure cleanup
- The `src/utils/` and `src/api/` directories exist but are empty (future work)
- MessageType enum inherits from str, allowing direct string comparison
- Python 3.13 requires sys.settrace inside thread, not threading.settrace before