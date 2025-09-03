# Capsule

A Python execution environment providing durable, async-first code execution with automatic recovery and distributed orchestration capabilities.

## What is Capsule?

Capsule is a **Subprocess-Isolated Execution Service (SIES)** that combines the isolation of separate processes with the persistence of stateful sessions. Built on an async-first architecture with Resonate SDK integration, Capsule provides:

- **Intelligent Execution Routing**: Automatically detects and routes code to the optimal executor (top-level await, async, blocking I/O, or simple sync)
- **Durable Sessions**: Crash recovery and distributed execution via Resonate promises
- **Capability-Based Architecture**: Secure, injectable functions for I/O, networking, and system operations
- **Native Top-Level Await**: Direct Python interpreter support using PyCF_ALLOW_TOP_LEVEL_AWAIT flag
- **Protocol-Based IPC**: Structured message passing with promise-based correlation
- **Language-Agnostic Core**: 70% of infrastructure is language-independent

## Key Features

### Execution Modes
- **Top-Level Await**: Native support via `PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x1000000`
- **Async Functions**: Full async/await with proper coroutine lifecycle
- **Blocking I/O**: Thread-based execution for requests, file operations
- **Simple Sync**: Direct execution for basic Python code

### Durability & Recovery
- **Automatic Crash Recovery**: Execution resumes from last checkpoint
- **Distributed Promises**: Cross-process correlation via Resonate
- **Transaction Support**: Rollback with configurable policies
- **Namespace Persistence**: State preserved across executions

### Performance
- Simple expression: <5ms latency
- Session acquisition: <100ms from warm pool
- Output streaming: <10ms latency
- Local mode overhead: <5% with Resonate
- Concurrent sessions: 100+ per manager

## Architecture

Capsule implements a three-layer architecture:

```
Application Layer (Resonate)
├── Durable Functions
├── Promise Management
└── Dependency Injection

Execution Layer (AsyncExecutor)
├── Execution Mode Analysis
├── Code Routing
└── Namespace Management

Protocol Layer (Transport)
├── Message Framing
├── Serialization
└── Correlation
```

## Installation

```bash
pip install capsule-exec
```

## Quick Start

### Basic Execution

```python
import asyncio
from capsule import Session

async def main():
    async with Session() as session:
        result = await session.execute("""
            x = 2 + 2
            print(f"The answer is {x}")
            x
        """)
        print(result.value)  # 4

asyncio.run(main())
```

### Top-Level Await

```python
async with Session() as session:
    await session.execute("""
        import asyncio
        await asyncio.sleep(1)
        result = await fetch_data()
        print(f"Got {len(result)} items")
    """)
```

### Interactive Input

```python
async with Session() as session:
    async for msg in session.stream_execute("""
        name = input("Your name: ")
        age = input("Your age: ")
        print(f"Hello {name}, age {age}")
    """):
        if msg.type == "input":
            response = "Alice" if "name" in msg.prompt else "25"
            await session.respond_input(msg.id, response)
        elif msg.type == "output":
            print(msg.data, end="")
```

### Durable Execution (Resonate Mode)

```python
from capsule import DurableSession

async with DurableSession(resonate_host="localhost:8001") as session:
    # Execution survives crashes and can resume
    result = await session.execute_durable(
        execution_id="data-processing-123",
        code="""
            df = load_large_dataset()
            processed = expensive_computation(df)
            save_results(processed)
        """,
        checkpoint_interval=10  # Checkpoint every 10 seconds
    )
```

## Development

```bash
# Install dev dependencies
pip install -e .[dev]

# Run tests
pytest

# Type checking
mypy src/
basedpyright src/

# Format
black src/
ruff format src/
```

## Language Support

Capsule's architecture separates language-agnostic infrastructure from language-specific execution:

- **Language-Agnostic (70%)**: Protocol, transport, session management, promises
- **Language-Specific (30%)**: Executor, AST analysis, serialization

This enables future support for JavaScript, Go, Rust, and other languages.

## License

MIT