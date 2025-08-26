# State Tracking

## Overview

Both implementations manage persistent Python execution state, but with fundamentally different architectural approaches:

- **exec-py**: Operation-centric with transactional namespace management
- **pyrepl2**: Session-centric with persistent subprocess interpreters

## exec-py/src/pyrepl Implementation

### Core State Management

The exec-py implementation tracks state at the **operation level** with transactional semantics:

```python
# exec-py/src/pyrepl/runner_async.py:208-213
op = Operation(op_id=op_id, code=code, tx_policy=tx_policy, timeout_ms=timeout_ms, runner=self)
# Snapshot namespace for transactional semantics
op.ns_snapshot = {k: v for k, v in self._global_ns.items()}
# Prepare op namespace (copy-on-write)
op.ns = {k: v for k, v in self._global_ns.items()}
```

### Key Components

1. **Operation Tracking** (`runner_async.py:97-118`):
```python
@dataclass
class Operation:
    op_id: str
    code: str
    tx_policy: str
    timeout_ms: int
    runner: AsyncRunner
    state: str = "PENDING"
    thread: threading.Thread | None = None
    cancelled: bool = False
    input_waiters: dict[str, InputWaiter] = field(default_factory=dict)
    ns_snapshot: dict[str, Any] = field(default_factory=dict)
    ns: dict[str, Any] = field(default_factory=dict)
```

2. **Global Namespace** (`runner_async.py:132`):
```python
# Shared persistent namespace (transactional semantics layered on top)
self._global_ns: dict[str, Any] = {"__builtins__": builtins}
```

3. **Transaction Policies** (`runner_async.py:257-263`):
```python
# Commit or rollback by policy
if op.tx_policy == "commit_on_success":
    self._global_ns.update(local_ns)
elif op.tx_policy == "explicit":
    pass
elif op.tx_policy == "rollback_on_failure":
    self._global_ns.update(local_ns)  # success => commit
```

### Tradeoffs

**Advantages:**
- Fine-grained transaction control per operation
- Automatic rollback on failure
- Lightweight namespace snapshots
- Thread-based parallelism for operations

**Disadvantages:**
- All operations share same process memory
- No true isolation between operations
- Thread safety complexity
- Limited by GIL for CPU-bound operations

## pyrepl2/pyrepl2 Implementation

### Core State Management

The pyrepl2 implementation maintains state at the **session level** with subprocess isolation:

```python
# pyrepl2/pyrepl2/implementations/base.py:142-157
context = SessionContext(
    session_id=session_id,
    sandbox_id=sandbox_id,
    subprocess=subprocess,
    state=SessionState.ACTIVE,
    created_at=datetime.now(UTC),
    execution_count=0,
)
```

### Key Components

1. **Session Context** (`implementations/base.py:654-672`):
```python
class SessionContext:
    """Internal session context."""
    def __init__(
        self,
        session_id: SessionId,
        sandbox_id: SandboxId,
        subprocess: SubprocessProtocol | None,
        state: SessionState,
        created_at: datetime,
        execution_count: int = 0,
    ):
        self.session_id = session_id
        self.sandbox_id = sandbox_id
        self.subprocess = subprocess
        self.state = state
```

2. **Persistent Interpreter** (`runner/interpreter.py:55-65`):
```python
def __init__(self) -> None:
    # Persistent namespace
    self.namespace: dict[str, Any] = {
        "__name__": "__main__",
        "__doc__": None,
        "__package__": None,
        "__loader__": None,
        "__spec__": None,
        "__annotations__": {},
        "__builtins__": __builtins__,
    }
```

3. **Change Detection** (`runner/interpreter.py:91-131`):
```python
def _detect_changes(self) -> dict[str, dict[str, Any]]:
    """Detect what changed in namespace since last snapshot."""
    changes = {}
    current_names = set(self.namespace.keys())
    snapshot_names = set(self.namespace_snapshot.keys())
    
    # Added entries
    for name in current_names - snapshot_names:
        obj = self.namespace[name]
        changes[name] = {
            "operation": "added",
            "type_name": type(obj).__name__,
            "size_bytes": self._get_size(obj),
            "serializable": self._is_serializable(obj),
        }
```

### Session States

pyrepl2 defines explicit session states (`types/execution.py:21-28`):

```python
class SessionState(StrEnum):
    ACTIVE = "active"  # Currently executing or ready
    IDLE = "idle"  # No recent activity
    CRASHED = "crashed"  # Subprocess died
    TERMINATED = "terminated"  # Explicitly destroyed
```

### Tradeoffs

**Advantages:**
- True process isolation between sessions
- Crash recovery capability
- Better security boundaries
- No GIL limitations
- Clean subprocess restart on failure

**Disadvantages:**
- Higher memory overhead per session
- IPC communication overhead
- More complex session lifecycle management
- Subprocess spawning latency

## Comparison Summary

| Aspect | exec-py | pyrepl2 |
|--------|---------|---------|
| **Isolation Model** | Thread-based operations | Process-based sessions |
| **State Scope** | Per-operation with global namespace | Per-session with isolated namespace |
| **Transaction Support** | Built-in with policies | Manual via checkpointing |
| **Memory Model** | Shared process memory | Isolated subprocess memory |
| **Crash Recovery** | Limited (thread crashes affect process) | Robust (subprocess can be restarted) |
| **Performance** | Lower latency, higher throughput | Higher latency, better isolation |
| **Complexity** | Simpler but thread-safety concerns | More complex but cleaner boundaries |

## Real-World Implications

### When to Use exec-py Approach:
- High-frequency, low-latency operations
- Trusted code execution
- Memory-constrained environments
- Need for fine-grained transaction control

### When to Use pyrepl2 Approach:
- Multi-tenant environments
- Untrusted code execution
- Long-running sessions
- Need for strong isolation guarantees
- Complex state management requirements

## Key Insight

The fundamental difference is **operation-centric vs session-centric** design:

- exec-py optimizes for transactional operations with lightweight isolation
- pyrepl2 optimizes for persistent sessions with strong isolation

This reflects different use cases: exec-py appears designed for rapid, controlled execution scenarios, while pyrepl2 targets persistent, isolated sandbox environments.