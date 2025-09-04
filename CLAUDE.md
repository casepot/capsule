# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Capsule is a Python execution environment implementing a **Subprocess-Isolated Execution Service (SIES)** pattern. It provides async-first code execution with automatic recovery and distributed orchestration through Resonate SDK integration.

**Current State**: Transitioning from ThreadedExecutor to AsyncExecutor architecture (v0.4.0-alpha). Both patterns are acceptable during this transition.

## Development Commands

```bash
# Install/sync dependencies
uv sync

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/test_executor.py

# Run specific test
uv run pytest tests/unit/test_executor.py::TestThreadedExecutor::test_simple_execution

# Run specific test with verbose output
uv run pytest tests/unit/test_executor.py::TestThreadedExecutor::test_simple_code_execution -xvs

# Run test categories
uv run pytest -m unit          # Fast unit tests  
uv run pytest -m integration   # Integration tests
uv run pytest -m e2e          # End-to-end tests

# Run tests with coverage
uv run pytest --cov=src --cov-report=term-missing
uv run pytest --cov=src --cov-report=html

# Run tests in parallel
uv run pytest -n auto

# Run fast tests only (exclude slow)
uv run pytest -m "not slow"

# Type checking
uv run mypy src/
uv run basedpyright src/

# Linting and formatting
uv run ruff check src/
uv run black src/
uv run ruff format src/

# Run tests with timeout protection
uv run pytest --timeout=30
```

## Architecture Overview

### Three-Layer Architecture

```
Application Layer (Future: Resonate SDK)
├── Durable Functions (planned)
├── Promise Management (transitioning)
└── Dependency Injection (planned)

Execution Layer 
├── ThreadedExecutor (current, for blocking I/O)
├── AsyncExecutor (implementing, for async/await)
└── NamespaceManager (merge-only policy)

Protocol Layer
├── MessageTransport (PipeTransport implementation)
├── Framing (4-byte length prefix + payload)
└── Messages (Pydantic models with MessagePack/JSON)
```

### Core Components

**Session Management** (`src/session/`):
- `Session`: Individual subprocess with persistent namespace
- `SessionPool`: Pre-warmed sessions for <100ms acquisition
- State transitions: CREATED → STARTING → IDLE/READY → BUSY → TERMINATED

**Execution** (`src/subprocess/`):
- `ThreadedExecutor`: Current implementation, runs user code in threads
- `AsyncExecutor`: Future implementation with execution mode routing
- `worker.py`: Main subprocess entry point

**Protocol** (`src/protocol/`):
- Binary framing with 4-byte length prefix
- Message types: Execute, Output, Input, Result, Error, Heartbeat
- Correlation via execution_id and message-specific IDs

### Critical Architectural Rules

1. **Namespace Management - NEVER REPLACE, ALWAYS MERGE**
   ```python
   # ❌ WRONG - Causes KeyError
   self._namespace = new_namespace
   
   # ✅ CORRECT - Preserves engine internals
   self._namespace.update(new_namespace)
   ```

2. **Event Loop Management**
   - Get/set loop BEFORE creating asyncio objects
   - All asyncio objects in a session must use same loop
   - ThreadedExecutor coordinates with main loop via `call_soon_threadsafe`

3. **Execution Mode Detection (Future)**
   - TOP_LEVEL_AWAIT: Use PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x1000000
   - ASYNC_DEF: AsyncExecutor
   - BLOCKING_SYNC: ThreadedExecutor  
   - SIMPLE_SYNC: Direct execution

## Current Transition Work

The codebase is transitioning from ThreadedExecutor to AsyncExecutor. Key files being modified:

### Phase 0 (Immediate Fixes)
- `src/subprocess/executor.py`: Add async wrapper to ThreadedExecutor
- `src/subprocess/worker.py`: Fix ResultMessage to include execution_time
- `src/subprocess/namespace.py`: Implement merge-only policy
- `src/session/manager.py`: Fix event loop management

### Phase 1 (Foundation)
- Create `src/subprocess/async_executor.py`: AsyncExecutor skeleton
- Update namespace management with ENGINE_INTERNALS protection
- Fix asyncio object creation order

### Phase 2 (Bridge Architecture)
- Add execution mode routing
- Create promise abstraction layer (pre-Resonate)
- Implement capability base classes

## Message Protocol Requirements

All messages must include required fields:
- `ResultMessage`: Must include `execution_time`
- `HeartbeatMessage`: Must include `memory_usage`, `cpu_percent`, `namespace_size`
- `CheckpointMessage`: Must include all data fields when present

Correlation patterns:
- `ExecuteMessage.id` → `execution_id` for all related messages
- `InputMessage.id` → `InputResponseMessage.input_id`

## Testing Patterns

Tests expect AsyncExecutor interface. During transition:
- Provide async wrappers for ThreadedExecutor
- Fix Pydantic validation by providing all required fields
- Handle event loop binding issues in fixtures
- Session reuse is mandatory (new Session() needs justification)

Test organization:
- `tests/unit/`: Component tests
- `tests/integration/`: Cross-component tests
- `tests/features/`: Feature-specific tests
- `tests/e2e/`: Full system tests
- `tests/fixtures/`: Shared test fixtures

## Key Specifications

Important specification documents in `docs/async_capability_prompts/current/`:
- `00_foundation_resonate.md`: Resonate SDK integration vision
- `10_prompt_async_executor.md`: AsyncExecutor implementation guide
- `22_spec_async_execution.md`: Execution mode detection and routing
- `24_spec_namespace_management.md`: Namespace merge-only policy

## Performance Targets

- Simple expression: <5ms
- Session acquisition (warm): <100ms  
- Output streaming latency: <10ms
- Local mode Resonate overhead: <5%
- Concurrent sessions: 100+ per manager

## Security Considerations

- Subprocess isolation for each session
- Capability-based security (future)
- Resource limits: 512MB memory, 30s timeout, 100 FDs per session
- Never use `dont_inherit=True` in compile() - breaks cancellation

## Common Pitfalls

1. **Replacing namespace dict**: Always merge, never replace
2. **Creating asyncio objects before setting loop**: Set loop first
3. **Missing message fields**: Check Pydantic model requirements
4. **Not handling InputMessage in tests**: Must respond with correct correlation ID
5. **Session state assumptions**: Check state before operations

## Debugging Tips

- Enable structlog debug output for protocol messages
- Use `pytest -vv` for verbose test output
- Check event loop binding with `asyncio.get_running_loop()`
- Monitor subprocess lifecycle via HeartbeatMessage
- Verify namespace preservation with ENGINE_INTERNALS keys