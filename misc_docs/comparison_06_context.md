# Execution Context

## Overview

The implementations manage execution context very differently:

- **exec-py**: Thread-local context with input handling and FD separation
- **pyrepl2**: Process-isolated context with session pooling and sandboxing

## exec-py/src/pyrepl Implementation

### Thread-Local Execution Context

Each operation has its own thread context (`runner_async.py:97-118`):

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
    started_at: float = field(default_factory=time.time)
```

### I/O Context Management

Custom I/O redirection within thread (`runner_async.py:244-256`):

```python
with (
    contextlib.redirect_stdout(cast("IO[str]", stdout)),
    contextlib.redirect_stderr(cast("IO[str]", stderr)),
):
    # Install helpers
    local_ns = op.ns
    local_ns["await_input"] = await_input
    local_ns["input"] = await_input  # v0.1.1: Override builtin input
    # Execute code
    exec(compile(code, "<exec>", "exec"), local_ns, local_ns)
    result_obj = local_ns.get("_")  # conventional last expression, if set
```

### FD Separation (v0.2)

Advanced file descriptor management (`manager.py:76-127`):

```python
# Check if we should use FD separation or fallback mode
use_fd_separation = (
    os.name != "nt"  # Not Windows
    and os.environ.get("PYREPL_FD_SEPARATION", "true").lower() == "true"
)

if use_fd_separation:
    try:
        # Use FD separation - protocol on dedicated FDs, stdio free for user
        child_env = dict(self.env) if self.env else {}
        child_env["PYREPL_PROTOCOL_FDS"] = f"{to_runner_r},{from_runner_w}"
        
        proc = await asyncio.create_subprocess_exec(
            *self.runner_cmd,
            stdin=None,  # Free for user code
            stdout=None,  # Free for user code
            stderr=asyncio.subprocess.PIPE,  # Capture stderr for debugging
            pass_fds=(to_runner_r, from_runner_w),  # Pass these exact FDs to child
            cwd=self.cwd,
            env=child_env,
        )
```

### Input Context

Interactive input with token-based correlation (`runner_async.py:315-360`):

```python
async def _handle_input_response(self, id_: str, op_id: str | None, payload: dict) -> None:
    # Get op_id from payload if not in frame
    if not op_id:
        op_id = payload.get("op_id")
    
    if not op_id or op_id not in self._ops:
        await self._send_error(
            id_,
            explain(
                ErrorCode.NOT_FOUND,
                what="Unknown operation for input_response",
                why=f"op_id={op_id!r} not tracked",
                how="Use the returned op_id from exec/exec_stream when sending input_response.",
            ),
        )
        return
    
    op = self._ops[op_id]
    token = payload.get("token")
    data = payload.get("data")
```

## pyrepl2/pyrepl2 Implementation

### Session Context

Rich session context with lifecycle management (`implementations/base.py:654-672`):

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
        self.created_at = created_at
        self.last_execution: datetime | None = None
        self.execution_count = execution_count
```

### Sandbox Context

Integration with sandbox environments (`implementations/daytona/execution.py:101-127`):

```python
async def _start_subprocess(self, sandbox_id: SandboxId) -> SubprocessProtocol:
    """
    Start interpreter subprocess in Daytona sandbox.
    """
    # Get or create sandbox
    sandbox = await self._get_or_create_sandbox(sandbox_id)
    
    # Upload interpreter script
    await self._upload_interpreter(sandbox, "/workspace/pyrepl_interpreter.py")
    
    # Create Daytona session for this interpreter
    daytona_session_id = f"pyrepl-{uuid.uuid4().hex[:8]}"
    await sandbox.process.create_session(session_id=daytona_session_id)
    
    # Create subprocess protocol
    protocol = DaytonaSubprocessProtocol(sandbox=sandbox, session_id=daytona_session_id)
    
    # Start the interpreter
    await protocol.start()
    
    return protocol
```

### Session Pool Context

Advanced pooling with lifecycle management (`pool/session_pool.py:48-74`):

```python
@dataclass
class PooledSession:
    """A session managed by the pool."""
    
    session_id: SessionId
    state: PooledSessionState
    created_at: datetime
    last_used: datetime
    use_count: int = 0
    sandbox_id: str | None = None
    error: str | None = None
    
    @property
    def age_seconds(self) -> float:
        """Age of session in seconds."""
        return (datetime.now(UTC) - self.created_at).total_seconds()
    
    @property
    def idle_seconds(self) -> float:
        """Time since last use in seconds."""
        return (datetime.now(UTC) - self.last_used).total_seconds()
    
    def is_expired(self, max_age_seconds: int, max_idle_seconds: int) -> bool:
        """Check if session is expired."""
        if self.state == PooledSessionState.ERROR:
            return True
        return self.age_seconds > max_age_seconds or self.idle_seconds > max_idle_seconds
```

### Resource Context

Resource limits and policies (`sandbox_types.py:18-29`):

```python
@dataclass(slots=True, frozen=True)
class ResourceLimits:
    """Resource limits for a sandbox (immutable)."""
    
    cpu_cores: float = 1.0
    memory_mb: int = 512
    disk_mb: int = 1024
    network_bandwidth_mbps: int | None = None
    max_processes: int = 10
    max_open_files: int = 100
    max_execution_time_seconds: float = 30.0
```

### Capability Injection

Platform-specific capability injection (`implementations/base.py:129-139`):

```python
async def _inject_default_capabilities(self, context: SessionContext) -> None:
    """
    Inject default capabilities into session.
    
    For Daytona, we might inject functions for:
    - File operations that sync with Daytona FS
    - Sandbox-specific utilities
    """
    # For now, no special capabilities
    # In the future, could inject Daytona-specific functions
    pass
```

## Context Management Comparison

| Feature | exec-py | pyrepl2 |
|---------|---------|---------|
| **Isolation Level** | Thread | Process + Sandbox |
| **Context Scope** | Per-operation | Per-session |
| **I/O Management** | Thread-local redirection | Process-level streams |
| **Resource Limits** | Not enforced | Configurable limits |
| **Capability Model** | Built-in helpers | Injectable functions |
| **Pool Support** | No | Yes, with warmup |
| **Sandbox Integration** | No | Daytona/platform-specific |
| **FD Management** | v0.2 separation | Process isolation |

## Context Lifecycle

### exec-py Operation Lifecycle

```
1. Create Operation object
2. Snapshot namespace
3. Spawn worker thread
4. Install I/O redirects
5. Execute code
6. Apply transaction policy
7. Clean up thread
```

### pyrepl2 Session Lifecycle

```
1. Create/acquire session from pool
2. Start subprocess in sandbox
3. Initialize interpreter
4. Inject capabilities
5. Execute code (multiple times)
6. Create checkpoints
7. Release to pool or destroy
```

## Advanced Context Features

### exec-py: Transaction Policies

```python
# Transaction policies control namespace commits
if op.tx_policy == "commit_on_success":
    self._global_ns.update(local_ns)
elif op.tx_policy == "explicit":
    pass  # No auto-commit
elif op.tx_policy == "rollback_on_failure":
    self._global_ns.update(local_ns)  # Only on success
```

### pyrepl2: Session Pool Warmup

```python
@profile_async(name="warm_session", category="pool")
async def _warm_session(self) -> None:
    """Warm a single session."""
    # Create session
    actual_session_id = await self._create_session()
    
    if actual_session_id:
        async with self._lock:
            # Add to idle pool
            session = self._sessions[actual_session_id]
            session.state = PooledSessionState.IDLE
            self._idle_sessions.append(actual_session_id)
            self._session_available.set()
```

## Security Context

### exec-py Security Model

- Shared process memory
- No built-in sandboxing
- Trust-based execution
- Limited by process permissions

### pyrepl2 Security Model

- Process isolation per session
- Sandbox environment support
- Resource limit enforcement
- Platform-specific security (Daytona)

## Performance Context

### exec-py Performance Characteristics

```python
# Lightweight operation creation
op = Operation(...)  # ~microseconds

# Fast namespace switching
op.ns = {k: v for k, v in self._global_ns.items()}  # ~milliseconds

# No subprocess overhead
exec(code, local_ns, local_ns)  # Direct execution
```

### pyrepl2 Performance Characteristics

```python
# Heavier session creation
session = await protocol.create_session(...)  # ~seconds

# But with pooling:
session_id = await pool.acquire()  # ~milliseconds if warm

# Subprocess communication overhead
result = await subprocess.call("execute", ...)  # IPC latency
```

## Use Case Alignment

### exec-py Context Best For:

- High-frequency operations
- Shared namespace scenarios
- Interactive REPLs
- Memory-constrained environments
- Trusted code execution

### pyrepl2 Context Best For:

- Multi-tenant environments
- Long-running sessions
- Resource-controlled execution
- Sandboxed environments
- Cloud/distributed execution

## Key Architectural Insight

The context models reflect fundamentally different trust and isolation requirements:

- **exec-py**: Designed for **trusted, high-performance** execution with lightweight context switching
- **pyrepl2**: Designed for **untrusted, isolated** execution with comprehensive resource control

exec-py optimizes for speed and simplicity in controlled environments, while pyrepl2 optimizes for safety and isolation in multi-tenant or cloud environments.