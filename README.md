# Capsule

> **Development Status**: 🚧 Experimental (v0.1.0-dev) - Phase 2c Complete, Phase 3 In Progress

A Python execution environment implementing subprocess isolation with persistent sessions and promise-based orchestration.

## Current State

Capsule is an experimental **Subprocess-Isolated Execution Service (SIES)** in active development. The project has completed its foundation phases (0-2c) with working subprocess isolation, promise-based message correlation, and local-mode durability through Resonate SDK.

### ✅ What's Working
- **Subprocess isolation** with persistent namespace across executions
- **ThreadedExecutor** for synchronous and blocking I/O code
- **Promise-based message correlation** via ResonateProtocolBridge
- **Input capability** for interactive code execution
- **Local-mode checkpoint/restore** for session state
- **Session pooling** for subprocess reuse
- **Single-loop invariant** with message interceptors

### 🚧 In Development (Phase 3)
- Native AsyncExecutor implementation (currently skeletal, delegates to ThreadedExecutor)
- Full top-level await support via PyCF_ALLOW_TOP_LEVEL_AWAIT
- Coroutine lifecycle management
- Execution cancellation

### ❌ Not Yet Implemented
- Full capability system (only Input capability exists)
- Remote Resonate mode (distributed execution)
- Performance optimizations beyond basic caching
- Production monitoring and observability
- Resource limits enforcement
- Multi-language support

## Test Coverage
- **Unit Tests**: 164/166 passing (98.8%)
- **Integration Tests**: 36/40 passing (90%)
- **Overall Coverage**: ~56%

## Architecture

Current implementation follows a three-layer architecture:

```
Protocol Layer (Working)
├── Message framing (4-byte prefix)
├── MessagePack/JSON serialization
└── Promise correlation

Execution Layer (Partial)
├── ThreadedExecutor (working)
├── AsyncExecutor (skeleton only)
└── NamespaceManager (working)

Integration Layer (Local Only)
├── ResonateProtocolBridge
├── Session interceptors
└── InputCapability
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

# Formatting
uv run black src/
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
│   │   ├── async_executor.py # AsyncExecutor (skeleton)
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

## Architectural Decisions

### Completed Decisions
- **Namespace Merge-Only Policy**: Never replace namespace dict, always merge
- **Single-Loop Invariant**: Session owns the sole event loop for transport
- **Promise-First Integration**: Durable functions use ctx.promise pattern
- **Capability-Based Security**: Security enforced at injection, not code analysis

### Pending Decisions (Phase 3+)
- Native async execution strategy (EventLoopCoordinator design)
- Capability registry architecture
- Remote mode connection management
- Performance optimization priorities

## Known Limitations

1. **AsyncExecutor is skeletal** - All code currently executes via ThreadedExecutor
2. **Local mode only** - No distributed execution yet
3. **Limited capabilities** - Only Input capability implemented
4. **No production features** - Missing metrics, monitoring, resource limits
5. **Test coverage gaps** - Some integration tests still failing

## Contributing

Capsule is in early development. Key areas needing contribution:

- Phase 3: Native AsyncExecutor implementation
- Phase 4: Capability system development
- Test coverage improvement
- Documentation
- Performance optimization

See [FOUNDATION_FIX_PLAN.md](FOUNDATION_FIX_PLAN.md) for detailed development status.

## License

MIT