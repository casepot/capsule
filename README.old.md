# PyREPL3

A subprocess-isolated execution service implementing session-oriented RPC with managed process pools and persistent namespaces.

PyREPL3 intends to provide production-ready Python code execution infrastructure with subprocess isolation, session management, interactive I/O support, and checkpoint/restore capabilities.

## Features

- **Subprocess Isolation**: Each session runs in an isolated subprocess for safety
- **Interactive Input**: Full input() support via thread-based execution model
- **Session Pooling**: Pre-warmed session pool for fast acquisition (<100ms)
- **Streaming Output**: Real-time streaming of stdout/stderr with <10ms latency
- **Transaction Support**: Rollback capabilities with configurable policies
- **Checkpoint/Restore**: Save and restore complete session state
- **Source Tracking**: Preserve function and class definitions
- **WebSocket & REST APIs**: Multiple client interfaces
- **Health Monitoring**: Automatic crash detection and recovery

## Technical Architecture

PyREPL3 implements a **Subprocess-Isolated Execution Service (SIES)** pattern - a managed stateful process pool with protocol-based IPC. This architecture pattern provides:

- **Session-Oriented RPC**: Maintains persistent state across multiple executions within a session
- **Process Isolation**: Each session runs in a separate subprocess with resource constraints
- **Managed Lifecycle**: Automatic health monitoring, restart on failure, and resource limit enforcement
- **Protocol-Based Communication**: Structured message passing over binary transport

The system consists of several key components:

- **Subprocess Worker**: Executes Python code in isolation
- **ThreadedExecutor**: Runs user code in dedicated threads, enabling blocking I/O
- **Protocol Layer**: Binary framed messages with JSON/MessagePack
- **Session Manager**: Lifecycle management of subprocess workers
- **Session Pool**: Pre-warming and efficient session reuse
- **Input Protocol**: INPUT/INPUT_RESPONSE messages for interactive code
- **Checkpoint System**: State serialization and restoration
- **API Layer**: WebSocket and REST interfaces

## Installation

```bash
pip install -e .
```

## Usage

### Basic Example

```python
import asyncio
from src.session.manager import Session
from src.protocol.messages import ExecuteMessage

async def main():
    # Create and start a session
    session = Session()
    await session.start()
    
    # Execute code
    message = ExecuteMessage(
        id="exec-1",
        timestamp=0,
        code="print('Hello from subprocess!')"
    )
    
    async for msg in session.execute(message):
        if msg.type == "output":
            print(msg.data)
    
    await session.shutdown()

asyncio.run(main())
```

### Interactive Input Example

```python
import asyncio
import time
from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType

async def main():
    session = Session()
    await session.start()
    
    # Code that uses input()
    code = """
name = input("What's your name? ")
age = input("How old are you? ")
print(f"Hello {name}, {age} years old!")
"""
    
    message = ExecuteMessage(
        id="interactive-1",
        timestamp=time.time(),
        code=code
    )
    
    # Execute and handle input requests
    async for msg in session.execute(message):
        if msg.type == MessageType.INPUT:
            # Respond to input request
            user_input = "Alice" if "name" in msg.prompt else "30"
            await session.input_response(msg.id, user_input)
        elif msg.type == MessageType.OUTPUT:
            print(msg.data, end="")
    
    await session.shutdown()

asyncio.run(main())
```

### Session Pool Example

```python
from src.session.pool import SessionPool, PoolConfig

# Configure pool
config = PoolConfig(
    min_idle=2,
    max_sessions=10,
    warmup_code="import numpy as np"
)

# Create and use pool
pool = SessionPool(config)
await pool.start()

session = await pool.acquire()
# Use session...
await pool.release(session)

await pool.stop()
```

## Language-Agnostic Design

While currently implementing Python execution, PyREPL3's architecture separates language-agnostic components from language-specific implementation:

- **Language-Agnostic (70%)**: Protocol layer, transport, session management, pooling, API layer
- **Language-Specific (30%)**: Worker subprocess, execution engine, serialization

This separation intends to enable future support for multiple languages (JavaScript, Haskell, etc.) by implementing language-specific workers that communicate via the same protocol.

## Performance

- Simple expression execution: <5ms
- Session acquisition (warm pool): <100ms
- Streaming output latency: <10ms
- Checkpoint size: <10MB for typical workloads
- Concurrent sessions: 100+ per manager

## Development

```bash
# Install dev dependencies
pip install -e .[dev]

# Run type checking
mypy src/
basedpyright src/

# Run tests
pytest

# Format code
black src/
```

## License

MIT# Trigger workflow test Sat Aug 30 23:21:54 EDT 2025
# Test new workflow Sat Aug 30 23:42:17 EDT 2025
