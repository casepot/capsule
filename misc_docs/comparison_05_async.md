# Async Code Execution

## Overview

Both implementations are built on asyncio but with different async patterns:

- **exec-py**: Event-driven architecture with thread workers and async event loops
- **pyrepl2**: Pure async/await with subprocess protocols and optional profiling

## exec-py/src/pyrepl Implementation

### Hybrid Threading + Async Model

exec-py uses threads for execution with async event delivery (`runner_async.py:283-310`):

```python
t = threading.Thread(target=_worker_body, name=f"op-{op_id}", daemon=True)
op.thread = t
t.start()

# Install timeout if requested
if timeout_ms > 0:
    async def _timeout():
        try:
            await asyncio.sleep(timeout_ms / 1000.0)
            if op.state not in ("COMPLETE", "CANCELLED", "FAILED"):
                op.mark_cancelled()
                self._send_event(
                    op_id,
                    {
                        "kind": "OP_FAILED",
                        "error": explain(
                            ErrorCode.TIMEOUT,
                            what="Operation timed out",
                            why=f"Exceeded timeout_ms={timeout_ms}",
                            how="Optimize the code or increase timeout_ms.",
                        ),
                    },
                )
        except asyncio.CancelledError:
            pass
    
    asyncio.create_task(_timeout())
```

### Thread-Safe Event Emission

exec-py bridges thread and async worlds (`runner_async.py:56-67`):

```python
class ThreadSafeEmitter:
    """Thread-safe event emitter from worker threads into the runner event loop."""
    
    def __init__(self, loop: asyncio.AbstractEventLoop, send: Callable[[str, Event], None], op_id: str) -> None:
        self.loop = loop
        self._send = send
        self.op_id = op_id
    
    def emit(self, event: Event) -> None:
        # Schedule send on the loop without blocking worker thread
        self.loop.call_soon_threadsafe(self._send, self.op_id, event)
```

### Async Message Pump

Main server loop is fully async (`runner_async.py:135-148`):

```python
async def serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Main message pump. SINGLE READER invariant lives here."""
    self._writer = writer
    try:
        while True:
            try:
                frame = await read_frame(reader)
            except EOFError:
                break
            await self._dispatch(frame)
    except asyncio.IncompleteReadError:
        # controller disconnected
        return
```

### Stream-Based I/O

Async stream handling with FD separation (`runner_async.py:406-445`):

```python
# v0.2: Check if protocol FDs are available
protocol_fds = os.environ.get("PYREPL_PROTOCOL_FDS", "")
if protocol_fds:
    try:
        # Parse the actual FD numbers from environment
        r_fd_str, w_fd_str = protocol_fds.split(",", 1)
        r_fd, w_fd = int(r_fd_str), int(w_fd_str)
        
        # v0.2 mode: Use dedicated FDs for protocol
        await loop.connect_read_pipe(lambda: protocol, os.fdopen(r_fd, "rb", buffering=0))
        w_transport, w_protocol = await loop.connect_write_pipe(
            lambda: asyncio.streams.FlowControlMixin(),
            os.fdopen(w_fd, "wb", buffering=0),
        )
```

### No Native Async Code Execution

exec-py doesn't support executing async Python code directly - all user code runs synchronously in threads.

## pyrepl2/pyrepl2 Implementation

### Pure Async Architecture

pyrepl2 uses async throughout (`implementations/base.py:133-180`):

```python
@profile_async(category="session_management")
async def create_session(
    self,
    sandbox_id: SandboxId,
    *,
    init_code: str | None = None,
    inject_capabilities: bool = True,
) -> Session:
    """Create a new persistent Python session."""
    session_id = SessionId(str(uuid.uuid4()))
    
    try:
        # Start subprocess (platform-specific)
        subprocess = await self._start_subprocess(sandbox_id)
        
        # Create session context
        context = SessionContext(
            session_id=session_id,
            sandbox_id=sandbox_id,
            subprocess=subprocess,
            state=SessionState.ACTIVE,
            created_at=datetime.now(UTC),
            execution_count=0,
        )
```

### Subprocess Protocol

JSON-RPC over async streams (`runner/protocol.py:106-150`):

```python
async def send_request(
    self,
    writer: asyncio.StreamWriter,
    reader: asyncio.StreamReader,
    method: str,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Send request and wait for response.
    """
    # Create request
    request_id, request = self.create_request(method, params)
    
    # Create future for response
    future = asyncio.Future()
    self._pending[request_id] = future
    
    try:
        # Send request
        writer.write(self.serialize_request(request))
        await writer.drain()
        
        # Wait for response with timeout
        response_data = await asyncio.wait_for(reader.readline(), timeout=timeout)
```

### Async Profiling Support

Optional async profiling decorators (`implementations/base.py:19-34`):

```python
try:
    from pyrepl2.profiling import profile_async, profile_method, get_profiler
    PROFILING_AVAILABLE = True
    _profiler = get_profiler()
except ImportError:
    PROFILING_AVAILABLE = False
    _profiler = None
    # Create no-op decorators
    def profile_async(name=None, category=None):
        def decorator(func):
            return func
        return decorator
```

### Session Pool with Async Warmup

Advanced async patterns in pool (`pool/session_pool.py:445-478`):

```python
@profile_async(name="ensure_min_idle", category="pool")
async def _ensure_min_idle_sessions(self) -> None:
    """Ensure minimum number of idle sessions."""
    # Determine how many sessions to create (with lock)
    tasks = []
    async with self._lock:
        idle_count = len(self._idle_sessions)
        warming_count = len(self._warming_sessions)
        total_count = len(self._sessions)
        
        # Calculate how many sessions to create
        target_idle = self.config.min_idle_sessions
        current_available = idle_count + warming_count
        needed = max(0, target_idle - current_available)
        
        # Create tasks (but don't wait yet - release lock first!)
        for _ in range(to_create):
            task = asyncio.create_task(self._warm_session())
            tasks.append(task)
    
    # Wait for tasks OUTSIDE the lock to avoid deadlock
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
```

### Async Interpreter Loop

The interpreter itself runs an async event loop (`runner/interpreter.py:566-623`):

```python
async def main_stdio() -> None:
    """Main async loop for stdin/stdout mode."""
    interpreter = PersistentInterpreter()
    
    # Read from stdin, write to stdout
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
    
    while True:
        try:
            # Read line from stdin
            line_bytes = await reader.readline()
            if not line_bytes:
                break  # EOF
```

### No Native Async Code Support

Like exec-py, pyrepl2 doesn't directly support executing async Python code - user code runs synchronously.

## Comparison Table

| Aspect | exec-py | pyrepl2 |
|--------|---------|---------|
| **Core Model** | Hybrid threading + async | Pure async/await |
| **Execution** | Threads with async events | Subprocess with async IPC |
| **Event Loop** | Single loop with thread callbacks | Multiple loops (main + subprocess) |
| **Concurrency** | Multiple operations in threads | Multiple sessions in subprocesses |
| **I/O Handling** | Async streams + thread-safe emission | Pure async streams |
| **Timeout Mechanism** | Async tasks monitoring threads | Async wait_for with timeout |
| **Profiling** | Not implemented | Optional async profiling |
| **Resource Management** | Manual thread lifecycle | Async context managers |
| **User Async Code** | ❌ Not supported | ❌ Not supported |

## Async Patterns Comparison

### Concurrent Operations

**exec-py:**
```python
# Multiple operations run in parallel threads
op1 = await client.exec_stream("long_computation()")
op2 = await client.exec_stream("another_computation()")
# Both run simultaneously in threads
```

**pyrepl2:**
```python
# Multiple sessions run in parallel subprocesses
result1 = asyncio.create_task(protocol.execute(session1, "long_computation()"))
result2 = asyncio.create_task(protocol.execute(session2, "another_computation()"))
# Both run simultaneously in subprocesses
```

### Resource Cleanup

**exec-py:**
```python
# Manual cleanup
op.mark_cancelled()
# Thread continues until next checkpoint
```

**pyrepl2:**
```python
# Structured cleanup
async with SessionPool(execution) as pool:
    session = await pool.acquire()
    try:
        result = await protocol.execute(session, code)
    finally:
        await pool.release(session)
```

## Performance Implications

### exec-py Async Performance

**Advantages:**
- Low overhead for event delivery
- Efficient thread pooling possible
- Minimal context switching for I/O

**Disadvantages:**
- GIL contention with multiple threads
- Thread creation overhead
- Complex synchronization

### pyrepl2 Async Performance

**Advantages:**
- True parallelism (no GIL)
- Clean async/await patterns
- Efficient subprocess pooling

**Disadvantages:**
- IPC overhead
- Subprocess creation latency
- Memory overhead per session

## Architectural Insights

### exec-py Philosophy
- **"Threads for CPU, async for I/O"**
- Uses threads to bypass GIL limitations for execution
- Async for efficient network/stream handling
- Event-driven architecture for real-time updates

### pyrepl2 Philosophy
- **"Async all the way down"**
- Consistent async patterns throughout
- Subprocess isolation for true parallelism
- Protocol-based communication

## Future Enhancement Possibilities

### Supporting Async User Code

Both implementations could support async code execution:

**exec-py approach:**
```python
# Run async code in thread's event loop
def execute_async(code):
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(eval(code))
    return result
```

**pyrepl2 approach:**
```python
# Add async execution method to interpreter
async def execute_async(self, code: str):
    # Create async function wrapper
    async_code = f"async def __exec():\n{indent(code)}"
    exec(async_code, self.namespace)
    return await self.namespace['__exec']()
```

## Key Takeaway

The async architectures reflect different priorities:

- **exec-py**: Optimized for **event streaming** with minimal latency
- **pyrepl2**: Optimized for **clean abstractions** and true parallelism

exec-py's hybrid model provides lower latency for events but more complexity, while pyrepl2's pure async model provides cleaner code and better isolation at the cost of IPC overhead.