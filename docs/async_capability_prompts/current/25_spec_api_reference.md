# API Reference Specification

## Document Information
- **Version**: 1.0.0
- **Status**: Draft
- **Last Updated**: 2025-01-03
- **Classification**: API Reference

## Executive Summary

This document provides comprehensive API documentation for PyREPL3, covering all public interfaces, method signatures, parameters, return types, and usage examples. The API is organized by component: Resonate Integration, AsyncExecutor, Capability System, and Namespace Management.

## API Organization

```
PyREPL3 API
├── Resonate Integration
│   ├── Initialization
│   ├── Durable Functions
│   ├── Dependencies
│   └── Promises
├── AsyncExecutor
│   ├── Execution
│   ├── Mode Detection
│   └── Coroutine Management
├── Capability System
│   ├── Capability Base
│   ├── Registry
│   └── Security Policy
└── Namespace Management
    ├── Core Operations
    ├── Persistence
    └── Synchronization
```

---

## Resonate Integration API

### Initialization

#### `initialize_resonate_local(session, resonate=None)`

Initialize Resonate in local mode and wire dependencies to a provided Session. (Ready)

**Signature:**
```python
from typing import Optional
from src.session.manager import Session

def initialize_resonate_local(session: Session, resonate: Optional[Resonate] = None) -> Resonate
```

**Parameters:**
- `session` (Session): The session that owns the transport and receive loop
- `resonate` (Optional[Resonate]): Existing instance to configure; creates `Resonate.local()` if None

**Returns:**
- `Resonate`: Configured instance with durable functions and DI registered

**Registers (DI):** `namespace_manager`, `protocol_bridge`, `input_capability`, `async_executor`

**Example:**
```python
from src.session.manager import Session
from src.integration.resonate_init import initialize_resonate_local

session = Session()
await session.start()
resonate = initialize_resonate_local(session)
```

---

#### `initialize_resonate_remote(...)`

Planned: Remote initializer is a design target, not implemented in this codebase.

Reference (planned design):
```python
def initialize_resonate_remote(
    host: str = "http://localhost:8001",
    api_key: Optional[str] = None,
    worker_group: str = "pyrepl3-workers",
    worker_id: Optional[str] = None
) -> Resonate:
    ...

# Example (planned)
resonate = initialize_resonate_remote(
    host="https://resonate-server.example.com",
    api_key="secret-key-123",
    worker_group="production-workers"
)
```

---

### Session Manager (Ready)

`Session` owns the worker subprocess and the single event loop that reads from the transport. Only the `Session` may read; all other components observe via interceptors or `execute()`.

Key methods:
- `await start()` / `await shutdown()` / `await restart()` / `await terminate()`
- `async for msg in execute(ExecuteMessage, timeout=None)` → streams Output/Result/Error/Input
- `await input_response(input_id: str, data: str)`
- `add_message_interceptor(fn)` / `remove_message_interceptor(fn)`

Single‑loop invariant: do not read the transport directly in tests or components.

### ResonateProtocolBridge (Ready → Beta)

`ResonateProtocolBridge(resonate, session)` sends protocol messages and resolves durable promises when responses are routed by session interceptors.

Correlation rules:
- Execute → Result/Error: `ExecuteMessage.id` (worker execution_id) ↔ durable id `exec:{execution_id}`
- Input → InputResponse: `InputMessage.id` ↔ durable id `{execution_id}:input:{message.id}`

The bridge never calls `receive_message`.

#### Correlation & Promise IDs (Phase 2)

- Execute: durable promise id `exec:{execution_id}` created by durable function; correlation key is `ExecuteMessage.id` and responses correlate on `{Result,Error}.execution_id`.
- Input: durable promise id `{execution_id}:input:{input_message.id}` created by the bridge; correlation key is `InputMessage.id` and response correlates on `InputResponseMessage.input_id`.

The bridge resolves on `ResultMessage` and rejects on `ErrorMessage`. On timeouts passed to `send_request`, a background task rejects with structured JSON containing `capability`, `execution_id`, `request_id`, and `timeout` seconds.

#### Error/Timeout Rejections (Phase 2)

- `ErrorMessage` → bridge calls `promises.reject(id=..., error=payload_json)`.
- Timeouts → bridge calls `promises.reject(...)` with JSON payload including context fields for reliability and diagnostics.
- Durable functions should expect promise rejections and raise structured exceptions with `add_note` context (at minimum, execution id, traceback excerpt if present).

#### Example: Execute request with deterministic promise id

```python
import time
from src.integration.resonate_bridge import ResonateProtocolBridge
from src.protocol.messages import ExecuteMessage

# Durable function (generator style)
def durable_execute(ctx, args):
    code = args["code"]
    execution_id = args["execution_id"]
    bridge: ResonateProtocolBridge = ctx.get_dependency("protocol_bridge")

    # Create deterministic promise id and yield it
    promise_id = f"exec:{execution_id}"
    promise_handle = yield ctx.promise(id=promise_id)

    # Build request; correlate request (ExecuteMessage.id) to the same promise id
    exec_msg = ExecuteMessage(
        id=execution_id,
        timestamp=time.time(),
        code=code,
        capture_source=True,
    )
    yield bridge.send_request(
        "execute", execution_id, exec_msg, timeout=30.0, promise_id=promise_id
    )

    # Await result or rejection
    try:
        raw = yield promise_handle
    except Exception as e:
        # Promise rejected (ErrorMessage or timeout). Add structured notes and re-raise.
        err = RuntimeError("durable_execute rejected")
        if hasattr(err, "add_note"):
            err.add_note(f"Execution ID: {execution_id}")
            err.add_note(str(e))
        raise err

    # Parse JSON payload for ResultMessage shape...
    # return parsed
```

### Durable Functions (Promise‑First) (Ready)

Generator pattern for durable execute:
```python
promise = yield ctx.promise(id=f"exec:{execution_id}")
exec_msg = ExecuteMessage(id=execution_id, timestamp=time.time(), code=code, capture_source=True)
yield bridge.send_request("execute", execution_id, exec_msg, timeout=ctx.config.tla_timeout, promise_id=f"exec:{execution_id}")
raw = yield promise  # JSON for ResultMessage/ErrorMessage
```

### Input Capability (Ready)

`InputCapability(resonate, bridge).request_input(prompt, execution_id)` sends `InputMessage` via the bridge and awaits the returned promise; safely parses `{ "input": "..." }`.

---

### Durable Functions

#### `@resonate.register`

Decorator to register a function as durable.

**Signature:**
```python
@resonate.register(
    name: Optional[str] = None,
    version: str = "1.0.0",
    timeout: Optional[int] = None,
    retries: int = 3,
    idempotent: bool = False,
    tags: Optional[List[str]] = None
)
```

**Parameters:**
- `name` (Optional[str]): Function name (defaults to function.__name__)
- `version` (str): Function version
- `timeout` (Optional[int]): Timeout in milliseconds
- `retries` (int): Number of retry attempts
- `idempotent` (bool): Whether function is idempotent
- `tags` (Optional[List[str]]): Tags for categorization

**Example:**
```python
@resonate.register(
    name="process_data",
    version="2.0.0",
    timeout=30000,
    retries=5,
    idempotent=True,
    tags=["data", "processing"]
)
def process_data(ctx, args):
    data = args['data']
    result = transform(data)
    return result
```

---

#### `DurableFunction.run()`

Execute durable function synchronously.

**Signature:**
```python
def run(
    execution_id: str,
    args: Dict[str, Any]
) -> Any
```

**Parameters:**
- `execution_id` (str): Unique execution identifier
- `args` (Dict[str, Any]): Function arguments

**Returns:**
- `Any`: Function result

**Example:**
```python
result = process_data.run(
    "exec-123",
    {"data": [1, 2, 3]}
)
```

---

#### `DurableFunction.rpc()`

Execute durable function asynchronously.

**Signature:**
```python
def rpc(
    execution_id: str,
    args: Dict[str, Any]
) -> Promise
```

**Parameters:**
- `execution_id` (str): Unique execution identifier
- `args` (Dict[str, Any]): Function arguments

**Returns:**
- `Promise`: Promise for eventual result

**Example:**
```python
promise = process_data.rpc(
    "exec-124",
    {"data": [4, 5, 6]}
)
result = await promise.result()
```

---

### Dependencies

#### `resonate.set_dependency()`

Register a dependency for injection.

**Signature:**
```python
def set_dependency(
    name: str,
    factory: Union[type, Callable],
    singleton: bool = True,
    lazy: bool = False,
    config: Optional[Dict] = None
)
```

**Parameters:**
- `name` (str): Dependency name
- `factory` (Union[type, Callable]): Factory function or class
- `singleton` (bool): Whether to create single instance
- `lazy` (bool): Whether to create on first access
- `config` (Optional[Dict]): Configuration for factory

**Example:**
```python
resonate.set_dependency(
    "database",
    lambda: DatabaseConnection(host="localhost"),
    singleton=True,
    lazy=True
)
```

---

#### `context.get_dependency()`

Retrieve a dependency in durable function.

**Signature:**
```python
def get_dependency(name: str) -> Any
```

**Parameters:**
- `name` (str): Dependency name

**Returns:**
- `Any`: Dependency instance

**Example:**
```python
@resonate.register
def query_data(ctx, args):
    db = ctx.get_dependency("database")
    return db.query(args['sql'])
```

---

### Promises

#### `resonate.promises.create()`

Create a new promise.

**Signature:**
```python
def create(
    id: str,
    timeout: Optional[int] = None,
    data: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> Promise
```

**Parameters:**
- `id` (str): Unique promise ID
- `timeout` (Optional[int]): Timeout in milliseconds
- `data` (Optional[str]): Associated data (JSON string)
- `tags` (Optional[List[str]]): Tags for categorization

**Returns:**
- `Promise`: Created promise

**Example:**
```python
promise = resonate.promises.create(
    id="user-input-123",
    timeout=300000,  # 5 minutes
    data=json.dumps({"prompt": "Enter name:"}),
    tags=["input", "hitl"]
)
```

---

#### `resonate.promises.resolve()`

Resolve a promise with a value.

**Signature:**
```python
def resolve(
    id: str,
    data: str
)
```

**Parameters:**
- `id` (str): Promise ID to resolve
- `data` (str): Resolution data (JSON string)

**Example:**
```python
resonate.promises.resolve(
    id="user-input-123",
    data=json.dumps({"input": "John Doe"})
)
```

---

#### `resonate.promises.reject()`

Reject a promise with an error.

**Signature:**
```python
def reject(
    id: str,
    error: str
)
```

**Parameters:**
- `id` (str): Promise ID to reject
- `error` (str): Error message

**Example:**
```python
resonate.promises.reject(
    id="user-input-123",
    error="User cancelled input"
)
```

---

## AsyncExecutor API (Skeleton / Transition)

### Core Execution

#### `AsyncExecutor.__init__()`

Initialize AsyncExecutor instance.

**Signature (current codebase):**
```python
def __init__(
    namespace_manager: NamespaceManager,
    transport: MessageTransport | None,
    execution_id: str,
    *,
    tla_timeout: float = 30.0,
    ast_cache_max_size: int | None = 100,
    blocking_modules: set[str] | None = None,
    blocking_methods_by_module: dict[str, set[str]] | None = None,
    warn_on_blocking: bool = True,
)
```

Note: Provided via a DI factory and not used in promise‑first durable flows. A full native async implementation is planned for later phases.

---

#### `AsyncExecutor.execute()`

Execute Python code with automatic mode detection.

**Signature:**
```python
async def execute(code: str) -> Any
```

**Parameters:**
- `code` (str): Python code to execute

**Returns:**
- `Any`: Execution result

**Example:**
```python
# Simple sync execution
result = await executor.execute("x = 1 + 2")

# Top-level await execution
result = await executor.execute(
    "import asyncio; result = await asyncio.sleep(0, 'done')"
)
```

**Exceptions:**
- `CompilationError`: If code cannot be compiled
- `ExecutionError`: If execution fails
- `CancellationError`: If execution is cancelled

---

### Mode Detection

#### `AsyncExecutor.analyze_execution_mode()`

Analyze code to determine execution mode.

**Signature:**
```python
def analyze_execution_mode(code: str) -> ExecutionMode
```

**Parameters:**
- `code` (str): Python code to analyze

**Returns:**
- `ExecutionMode`: Detected execution mode

**Execution Modes:**
- `TOP_LEVEL_AWAIT`: Contains top-level await
- `ASYNC_DEF`: Contains async function definitions
- `BLOCKING_SYNC`: Contains blocking I/O operations
- `SIMPLE_SYNC`: Simple synchronous code
- `UNKNOWN`: Cannot determine mode

**Example:**
```python
mode = executor.analyze_execution_mode(
    "await asyncio.sleep(1)"
)
assert mode == ExecutionMode.TOP_LEVEL_AWAIT
```

---

### Coroutine Management

#### `AsyncExecutor.track_coroutine()`

Track a coroutine for lifecycle management.

**Signature:**
```python
def track_coroutine(coro: Coroutine)
```

**Parameters:**
- `coro` (Coroutine): Coroutine to track

**Example:**
```python
async def my_coro():
    return "result"

coro = my_coro()
executor.track_coroutine(coro)
```

---

#### `AsyncExecutor.cleanup_coroutines()`

Clean up pending coroutines.

**Signature:**
```python
def cleanup_coroutines() -> int
```

**Returns:**
- `int`: Number of coroutines cleaned

**Example:**
```python
cleaned = executor.cleanup_coroutines()
print(f"Cleaned {cleaned} coroutines")
```

---

## Capability System API

### Capability Base Class

#### `Capability.__init__()`

Initialize capability instance.

**Signature:**
```python
def __init__(
    resonate: Resonate,
    capability_type: CapabilityType,
    execution_id: str
)
```

**Parameters:**
- `resonate` (Resonate): Resonate instance
- `capability_type` (CapabilityType): Type of capability
- `execution_id` (str): Execution context ID

---

#### `Capability.get_name()`

Get capability name.

**Signature:**
```python
@abstractmethod
def get_name() -> str
```

**Returns:**
- `str`: Capability name

---

#### `Capability.get_implementation()`

Get capability implementation function.

**Signature:**
```python
@abstractmethod
def get_implementation() -> Callable
```

**Returns:**
- `Callable`: Implementation function

---

#### `Capability.create_promise()`

Create promise for capability operation.

**Signature:**
```python
def create_promise(
    operation: str,
    data: Dict[str, Any],
    timeout: Optional[float] = None
) -> Promise
```

**Parameters:**
- `operation` (str): Operation name
- `data` (Dict[str, Any]): Operation data
- `timeout` (Optional[float]): Timeout in seconds

**Returns:**
- `Promise`: Created promise

---

### Capability Registry

#### `CapabilityRegistry.register_capability()`

Register a capability class.

**Signature:**
```python
def register_capability(
    capability_class: type,
    name: Optional[str] = None
)
```

**Parameters:**
- `capability_class` (type): Capability class
- `name` (Optional[str]): Override name

**Example:**
```python
registry = CapabilityRegistry(resonate)
registry.register_capability(InputCapability, "input")
registry.register_capability(PrintCapability)  # Uses default name
```

---

#### `CapabilityRegistry.get_capability()`

Get capability instance.

**Signature:**
```python
def get_capability(
    name: str,
    execution_id: str
) -> Optional[Capability]
```

**Parameters:**
- `name` (str): Capability name
- `execution_id` (str): Execution context

**Returns:**
- `Optional[Capability]`: Capability instance or None

**Example:**
```python
input_cap = registry.get_capability("input", "exec-789")
if input_cap:
    impl = input_cap.get_implementation()
```

---

#### `CapabilityRegistry.inject_capabilities()`

Inject capabilities into namespace.

**Signature:**
```python
def inject_capabilities(
    namespace: Dict[str, Any],
    execution_id: str,
    security_policy: SecurityPolicy
) -> Dict[str, Any]
```

**Parameters:**
- `namespace` (Dict[str, Any]): Target namespace
- `execution_id` (str): Execution context
- `security_policy` (SecurityPolicy): Security policy

**Returns:**
- `Dict[str, Any]`: Updated namespace

**Example:**
```python
namespace = {}
policy = SecurityPolicy(SecurityLevel.STANDARD)
registry.inject_capabilities(
    namespace,
    "exec-890",
    policy
)
# namespace now contains allowed capabilities
```

---

### Security Policy

#### `SecurityPolicy.__init__()`

Initialize security policy.

**Signature:**
```python
def __init__(
    level: SecurityLevel = SecurityLevel.STANDARD,
    custom_allowed: Optional[Set[str]] = None,
    custom_blocked: Optional[Set[str]] = None
)
```

**Parameters:**
- `level` (SecurityLevel): Base security level
- `custom_allowed` (Optional[Set[str]]): Additional allowed
- `custom_blocked` (Optional[Set[str]]): Explicitly blocked

**Security Levels:**
- `SANDBOX`: Minimal capabilities (print, display)
- `RESTRICTED`: Local I/O only
- `STANDARD`: Network + I/O
- `TRUSTED`: Most capabilities
- `UNRESTRICTED`: All capabilities

**Example:**
```python
policy = SecurityPolicy(
    level=SecurityLevel.RESTRICTED,
    custom_allowed={"fetch"},  # Add network fetch
    custom_blocked={"write_file"}  # Block file writes
)
```

---

#### `SecurityPolicy.is_allowed()`

Check if capability is allowed.

**Signature:**
```python
def is_allowed(capability_name: str) -> bool
```

**Parameters:**
- `capability_name` (str): Capability name

**Returns:**
- `bool`: Whether capability is allowed

**Example:**
```python
if policy.is_allowed("input"):
    # Input capability is allowed
    pass
```

---

## Namespace Management API

### Core Operations

#### `DurableNamespaceManager.__init__()`

Initialize namespace manager.

**Signature:**
```python
def __init__(
    resonate: Resonate,
    execution_id: str,
    config: Optional[NamespaceConfig] = None
)
```

**Parameters:**
- `resonate` (Resonate): Resonate instance
- `execution_id` (str): Unique execution ID
- `config` (Optional[NamespaceConfig]): Configuration

**Example:**
```python
config = NamespaceConfig(
    auto_persist=True,
    min_persist_interval=5.0
)
manager = DurableNamespaceManager(
    resonate,
    "exec-234",
    config
)
```

---
#### `DurableNamespaceManager.namespace`

Get namespace snapshot.

**Signature:**
```python
@property
def namespace() -> Dict[str, Any]
```

**Returns:**
- `Dict[str, Any]`: Namespace snapshot

**Example:**
```python
namespace = manager.namespace
print(namespace.get('x'))  # Safe read-only access
```

---

#### `DurableNamespaceManager.update_namespace()`

**CRITICAL**: Update namespace (never replaces, always merges).

**Signature:**
```python
def update_namespace(
    updates: Dict[str, Any],
    source_context: str = "unknown",
    merge_strategy: str = "overwrite"
) -> Dict[str, Any]
```

**Parameters:**
- `updates` (Dict[str, Any]): Updates to merge
- `source_context` (str): Source of updates
- `merge_strategy` (str): Merge strategy

**Merge Strategies:**
- `overwrite`: Always update values
- `preserve`: Only add new keys
- `smart`: Update if meaningful change

**Returns:**
- `Dict[str, Any]`: Actual changes made

**Example:**
```python
changes = manager.update_namespace(
    {"x": 42, "y": "hello"},
    source_context="user",
    merge_strategy="smart"
)
```

---

## Usage Examples

### Complete Execution Flow

```python
import asyncio
from pyrepl3 import (
    initialize_resonate_local,
    AsyncExecutor,
    DurableNamespaceManager,
    CapabilityRegistry,
    SecurityPolicy,
    SecurityLevel
)

async def main():
    # Initialize system
    resonate = initialize_resonate_local()
    
    # Create namespace manager
    namespace_manager = DurableNamespaceManager(
        resonate,
        "example-exec"
    )
    
    # Create executor
    executor = AsyncExecutor(
        resonate,
        namespace_manager,
        "example-exec"
    )
    
    # Set up capabilities
    registry = CapabilityRegistry(resonate)
    register_standard_capabilities(registry)
    
    # Apply security policy
    policy = SecurityPolicy(SecurityLevel.STANDARD)
    namespace = namespace_manager.namespace
    registry.inject_capabilities(
        namespace,
        "example-exec",
        policy
    )
    
    # Execute code
    await executor.execute("x = 42")
    await executor.execute("print(f'x = {x}')")
    
    # Persist namespace
    namespace_manager.persist_to_resonate()
    
    # Cleanup
    namespace_manager.cleanup_coroutines()

# Run
asyncio.run(main())
```

---

## Error Handling

### Common Exceptions

```python
try:
    result = await executor.execute(code)
except CompilationError as e:
    print(f"Code compilation failed: {e}")
except AsyncContextError as e:
    print(f"Async context error: {e}")
except ExecutionError as e:
    print(f"Execution failed: {e}")
```

---

## Best Practices Summary

1. **Thread Safety**: Always use proper context for execution
2. **Namespace Integrity**: Never replace, always merge
3. **Security First**: Enforce at capability injection
4. **Performance**: Enable caching and batching
5. **Cleanup**: Track and clean coroutines

---

## API Version: 1.0.0

This API reference is based on the REFINED prompt specifications for PyREPL3.
