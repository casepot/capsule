# Other Notable Differences and Observations

## Overview

Beyond the major architectural differences, there are numerous design patterns, error handling approaches, and implementation details that distinguish the two projects.

## Protocol Design

### exec-py: Custom Binary Protocol

exec-py implements a custom length-prefixed JSON protocol (`protocol.py:20-122`):

```python
LEN_STRUCT = struct.Struct(">I")  # 4-byte big-endian length

def frame(data: bytes) -> bytes:
    """Add length prefix to data."""
    return LEN_STRUCT.pack(len(data)) + data

async def write_frame(w, frame: Frame) -> None:
    data = json.dumps(frame.to_dict(), separators=(",", ":")).encode("utf-8")
    w.write(LEN_STRUCT.pack(len(data)))
    w.write(data)
    await w.drain()
```

Frame structure (`protocol.py:59-77`):
```python
@dataclass
class Frame:
    id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    op_id: str | None = None
    error: Error | None = None
    ts_ms: int = field(default_factory=lambda: int(time.time() * 1000))
```

### pyrepl2: Standard JSON-RPC 2.0

pyrepl2 uses industry-standard JSON-RPC (`runner/protocol.py:44-52`):

```python
request: JSONRPCRequest = {
    "jsonrpc": "2.0",
    "id": request_id,
    "method": method,
    "params": params or {},
}
```

Response handling (`types/execution.py:256-263`):
```python
class JSONRPCResponse(TypedDict):
    """JSON-RPC response message."""
    
    jsonrpc: str
    id: str
    result: dict[str, Any] | None
    error: dict[str, Any] | None
```

## Error Handling Philosophy

### exec-py: Explainable Errors

exec-py emphasizes detailed error explanations (`protocol.py:40-55`):

```python
@dataclass
class Error:
    code: ErrorCode
    what: str
    why: str
    how: str
    details: dict[str, Any] = field(default_factory=dict)

class ExplainableError(TypedDict):
    """Structured error that always explains what/why/how."""
    
    code: ErrorCode
    what: str
    why: str
    how: str
```

Error creation pattern (`runner_async.py:36-37`):
```python
def explain(code: ErrorCode, what: str, why: str, how: str) -> ExplainableError:
    return {"code": code, "what": what, "why": why, "how": how}
```

### pyrepl2: Exception Hierarchy

pyrepl2 uses traditional Python exceptions (`types/execution.py:160-241`):

```python
class ExecutionError(Exception):
    """Base error for execution operations."""
    pass

class SessionNotFoundError(ExecutionError):
    """Session doesn't exist."""
    
    def __init__(self, session_id: SessionId):
        super().__init__(f"Session {session_id} not found")
        self.session_id = session_id

class ExecutionTimeoutError(ExecutionError):
    """Execution exceeded timeout."""
    
    def __init__(self, session_id: SessionId, timeout: float):
        super().__init__(f"Execution in {session_id} timed out after {timeout}s")
        self.session_id = session_id
        self.timeout = timeout
```

## API Design

### exec-py: WebSocket + REST Hybrid

exec-py provides both WebSocket and REST endpoints (`api_server.py:66-186`):

```python
@app.websocket("/v1/exec_stream")
async def ws_exec_stream(ws: WebSocket) -> None:
    await ws.accept()
    # Bidirectional WebSocket for streaming execution
    
@app.post("/checkpoint")
async def checkpoint() -> JSONResponse:
    client = await get_client()
    return JSONResponse(await client.checkpoint())
```

### pyrepl2: Protocol-First Design

pyrepl2 defines protocols that implementations must follow (`protocols/execution.py:23-47`):

```python
class SandboxExecutionProtocol(Protocol):
    """Protocol for persistent Python execution within sandboxes.
    
    Key features:
    - Persistent interpreter sessions with full state retention
    - Namespace inspection and manipulation
    - Checkpoint/restore for session state
    - Capability injection for agent functions
    - Automatic crash recovery
    """
```

## Type Safety

### exec-py: Mixed Typing

exec-py uses TypedDict for protocol messages (`protocol.py:125-145`):

```python
class ExecRequest(TypedDict):
    code: str
    tx_policy: str
    timeout_ms: int

class OutputEvent(TypedDict):
    kind: str
    stream: str
    data: str
```

### pyrepl2: Strong Typing

pyrepl2 uses NewType and dataclasses extensively (`types/execution.py:17-18`):

```python
# Strong type identifiers
SessionId = NewType("SessionId", str)
CheckpointId = NewType("CheckpointId", str)
```

With frozen dataclasses (`types/execution.py:39-64`):
```python
@dataclass(slots=True, frozen=True)
class Session:
    """Persistent Python interpreter session."""
    
    session_id: SessionId
    sandbox_id: SandboxId
    state: SessionState
    created_at: datetime
    # ... more fields
```

## Testing Infrastructure

### exec-py: Injection Support

exec-py supports test injection (`manager.py:44-47`):

```python
# test injection (use inproc pipes or mocks)
reader: asyncio.StreamReader | None = None,
writer: asyncio.StreamWriter | None = None,
```

### pyrepl2: Mock Implementations

pyrepl2 provides mock implementations (`implementations/mock/local.py`):
```python
# Feature not present in exec-py
```

## Metrics and Observability

### exec-py: Basic Metrics

Simple operation tracking (`runner_async.py:68-70`):
```python
# Execution tracking
self.execution_count = 0
self.total_execution_time_ms = 0.0
```

### pyrepl2: Comprehensive Metrics

Detailed metrics tracking (`pool/session_pool.py:97-133`):

```python
@dataclass
class PoolMetrics:
    """Metrics for session pool performance."""
    
    total_sessions_created: int = 0
    total_sessions_reused: int = 0
    total_sessions_expired: int = 0
    total_sessions_errored: int = 0
    
    acquire_requests: int = 0
    acquire_hits: int = 0  # Served from IDLE pool
    acquire_misses: int = 0  # Had to create new session
    acquire_waits: int = 0  # Had to wait for session
    
    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0-1)."""
        if self.acquire_requests == 0:
            return 0.0
        return self.acquire_hits / self.acquire_requests
```

With profiling support (`implementations/base.py:19-34`):
```python
try:
    from pyrepl2.profiling import profile_async, profile_method, get_profiler
    PROFILING_AVAILABLE = True
except ImportError:
    PROFILING_AVAILABLE = False
```

## Platform Support

### exec-py: Cross-Platform with Limitations

FD separation only on Unix (`manager.py:83-86`):
```python
use_fd_separation = (
    os.name != "nt"  # Not Windows
    and os.environ.get("PYREPL_FD_SEPARATION", "true").lower() == "true"
)
```

### pyrepl2: Platform-Agnostic with Adapters

Multiple implementation backends:
- Daytona sandboxes
- Local subprocess
- Mock implementations

## Version Evolution

### exec-py: Version Comments

Version tracking in comments (`__init__.py:1`):
```python
"""v0.2 implementation - async event-driven runner with FD separation for true stdio freedom."""
```

### pyrepl2: Semantic Versioning

Standard versioning (`__init__.py:33`):
```python
__version__ = "0.1.0"
```

## Code Organization

### exec-py Structure
```
exec-py/src/pyrepl/
├── __init__.py         # Main exports
├── api_server.py       # FastAPI server
├── client.py           # Client implementation
├── manager.py          # Runner management
├── protocol.py         # Protocol definitions
├── runner.py           # Legacy runner
└── runner_async.py     # Async runner
```

### pyrepl2 Structure
```
pyrepl2/pyrepl2/
├── __init__.py              # Main exports
├── protocols/               # Protocol definitions
├── types/                   # Type definitions
├── implementations/         # Platform implementations
│   ├── base.py             # Base implementation
│   ├── daytona/            # Daytona backend
│   └── mock/               # Mock backend
├── runner/                  # Interpreter implementation
├── pool/                    # Session pooling
└── profiling/              # Performance profiling
```

## Documentation Style

### exec-py: Inline Comments

Brief docstrings with inline explanations:
```python
def _sanitize_ns(ns: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in ns.items():
        if k == "__builtins__" or (k.startswith("__") and k.endswith("__")):
            continue
        # exclude modules and callables
        if callable(v) or getattr(v, "__name__", None) == "module":
            continue
```

### pyrepl2: Comprehensive Docstrings

Detailed protocol documentation:
```python
async def execute(
    self,
    session_id: SessionId,
    code: str,
    *,
    timeout: float = 30.0,
) -> ExecutionResult:
    """Execute code in a persistent session.
    
    Executes Python code in the session's namespace. All variables,
    functions, classes, and imports persist for future executions.
    
    Args:
        session_id: Session to execute in
        code: Python code to execute
        timeout: Maximum execution time in seconds
    
    Returns:
        Execution result with output and namespace changes
    
    Raises:
        SessionNotFoundError: If session doesn't exist
        ExecutionTimeoutError: If execution exceeds timeout
        SessionCrashedError: If subprocess died during execution
    
    Example:
        ```python
        # First execution
        result = await protocol.execute(session_id, "x = 42")
        
        # Second execution - x persists
        result = await protocol.execute(session_id, "print(x)")
        # Output: "42"
        ```
    """
```

## Key Architectural Decisions Summary

| Aspect | exec-py | pyrepl2 |
|--------|---------|---------|
| **Core Philosophy** | Event-driven streaming | Protocol-based abstractions |
| **Primary Use Case** | Interactive REPL | Persistent sandboxed sessions |
| **Isolation Model** | Thread-based | Process-based |
| **Protocol** | Custom binary | JSON-RPC 2.0 |
| **Error Philosophy** | Explainable (what/why/how) | Exception hierarchy |
| **Type Safety** | Mixed | Strong |
| **Testing** | Injection support | Mock implementations |
| **Metrics** | Basic | Comprehensive with profiling |
| **Documentation** | Inline | Comprehensive docstrings |

## Final Observations

1. **Maturity Level**: pyrepl2 appears more mature with better abstractions, while exec-py seems more experimental with version comments and evolving features.

2. **Target Audience**: exec-py targets developers needing fast, interactive execution. pyrepl2 targets platform builders needing robust, isolated execution.

3. **Complexity**: exec-py is simpler but with hidden complexity in thread management. pyrepl2 is more complex upfront but with cleaner boundaries.

4. **Extensibility**: pyrepl2's protocol-based design makes it easier to add new backends. exec-py's monolithic design is harder to extend.

5. **Production Readiness**: pyrepl2 has more production-oriented features (pooling, metrics, profiling). exec-py is leaner but may need additional work for production use.

## Conclusion

Both implementations solve the persistent Python execution problem but for different scenarios:

- **exec-py** excels at low-latency, high-throughput scenarios with trusted code
- **pyrepl2** excels at isolated, long-running sessions with comprehensive state management

The choice between them depends on specific requirements around isolation, performance, and feature completeness.