# Unified PyREPL System Planning

## Mission

Design and implement a Python REPL execution system with persistent sessions, real-time streaming output, interactive input handling, comprehensive state management, and session pooling.

## System Architecture

### Component Overview

```
┌─────────────┐       ┌─────────────┐       ┌──────────────┐
│   Client    │──────▶│   Manager   │──────▶│  Subprocess  │
│ (WebSocket) │◀──────│  (Router)   │◀──────│   (Async)    │
└─────────────┘       └─────────────┘       └──────────────┘
                            │                      │
                            ▼                      ▼
                      ┌──────────┐          ┌──────────┐
                      │   Pool   │          │Namespace │
                      └──────────┘          └──────────┘
```

### Subprocess Architecture

Each session runs as a long-lived Python subprocess with:

**Core Components:**
- Single async event loop for all operations
- Persistent namespace dictionary across executions
- AST-based source tracking for function/class definitions
- Streaming output capture via async stdout/stderr redirection
- Protocol-based input handling (no direct stdin access)

**Execution Flow:**
```python
async def execute(self, code: str, transaction_policy: str) -> None:
    # Transaction snapshot
    snapshot = dict(self.namespace) if transaction_policy != "commit_always" else None
    
    # Parse and extract source definitions
    tree = ast.parse(code)
    self._extract_function_sources(tree)
    self._extract_class_sources(tree)
    
    # Execute with streaming output
    async with self._capture_output() as (stdout_stream, stderr_stream):
        try:
            # Compile and execute in namespace
            compiled = compile(tree, "<session>", "exec")
            exec(compiled, self.namespace, self.namespace)
            
            # Stream output as produced
            async for line in stdout_stream:
                await self._send_event({
                    "type": "OUTPUT",
                    "stream": "stdout",
                    "data": line,
                    "timestamp": time.time()
                })
                
            # Send result
            await self._send_event({
                "type": "RESULT",
                "success": True,
                "execution_time_ms": elapsed_ms
            })
            
        except Exception as e:
            # Transaction rollback
            if transaction_policy == "rollback_on_failure" and snapshot:
                self.namespace = snapshot
                
            await self._send_event({
                "type": "ERROR",
                "exception": type(e).__name__,
                "message": str(e),
                "traceback": traceback.format_exc()
            })
```

### Manager Architecture

The manager orchestrates sessions and client connections:

**Session Pool:**
```python
class SessionPool:
    """Pre-warmed subprocess pool for low-latency acquisition."""
    
    def __init__(self, config: PoolConfig):
        self.min_idle = config.min_idle  # Minimum idle sessions
        self.max_idle = config.max_idle  # Maximum idle sessions
        self.max_total = config.max_total  # Total session limit
        self.session_ttl = config.session_ttl  # Time-to-live in seconds
        
        self._idle: deque[SessionInfo] = deque()
        self._active: dict[SessionId, SessionInfo] = {}
        self._metrics = PoolMetrics()
        
    async def acquire(self, timeout: float = 5.0) -> SessionId:
        """Acquire session from pool or create new."""
        # Check idle pool first
        while self._idle:
            session = self._idle.popleft()
            if not session.is_expired():
                self._active[session.id] = session
                self._metrics.record_hit()
                return session.id
                
        # Create new if under limit
        if len(self._active) < self.max_total:
            session = await self._create_session()
            self._active[session.id] = session
            self._metrics.record_miss()
            return session.id
            
        # Wait for available session
        return await self._wait_for_available(timeout)
```

**Request Routing:**
- Receives JSON-RPC requests from clients
- Routes to session subprocess via protocol
- Aggregates and forwards streamed events
- Manages session lifecycle

### Protocol Specification

**Message Format:**

All messages use JSON encoding with type discrimination:

```typescript
// Client → Manager → Subprocess
interface ExecuteRequest {
    jsonrpc: "2.0";
    id: string;
    method: "execute";
    params: {
        session_id: string;
        code: string;
        transaction_policy: "commit_always" | "commit_on_success" | "rollback_on_failure";
        timeout_ms?: number;
    };
}

// Subprocess → Manager → Client (Streamed)
interface OutputEvent {
    type: "OUTPUT";
    session_id: string;
    stream: "stdout" | "stderr";
    data: string;
    timestamp: number;
}

interface InputRequest {
    type: "INPUT_REQUEST";
    session_id: string;
    token: string;
    prompt: string;
    timeout_ms?: number;
}

// Client → Manager → Subprocess
interface InputResponse {
    jsonrpc: "2.0";
    id: string;
    method: "input_response";
    params: {
        session_id: string;
        token: string;
        data: string;
    };
}
```

**Transport Layer:**
- Length-prefixed framing: 4-byte big-endian length + JSON payload
- Single bidirectional channel per subprocess
- asyncio.StreamReader/StreamWriter for subprocess communication
- WebSocket for client connections

## Technical Requirements

### Streaming Output

**Implementation:**
```python
class OutputCapture:
    """Async context manager for output capture with streaming."""
    
    async def __aenter__(self):
        self.stdout_queue = asyncio.Queue()
        self.stderr_queue = asyncio.Queue()
        
        # Redirect stdout/stderr to async queues
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = AsyncStreamWriter(self.stdout_queue)
        sys.stderr = AsyncStreamWriter(self.stderr_queue)
        
        # Start streaming tasks
        self._tasks = [
            asyncio.create_task(self._stream_queue(self.stdout_queue, "stdout")),
            asyncio.create_task(self._stream_queue(self.stderr_queue, "stderr"))
        ]
        
        return self
        
    async def _stream_queue(self, queue: asyncio.Queue, stream_name: str):
        """Stream output from queue to protocol."""
        while True:
            line = await queue.get()
            if line is None:  # Sentinel
                break
            await self._send_output_event(stream_name, line)
```

**Performance Requirements:**
- Maximum 10ms latency from print() to client receipt
- Buffer at most one line before sending
- Maintain output order across stdout/stderr

### Interactive Input

**Namespace Override:**
```python
def create_input_override(self):
    """Create input() replacement that uses protocol."""
    
    async def protocol_input(prompt: str = "") -> str:
        # Generate unique token
        token = str(uuid.uuid4())
        
        # Send input request
        await self._send_event({
            "type": "INPUT_REQUEST",
            "token": token,
            "prompt": prompt
        })
        
        # Wait for response
        future = self._input_futures[token] = asyncio.Future()
        try:
            response = await asyncio.wait_for(future, timeout=30.0)
            return response
        finally:
            del self._input_futures[token]
    
    # Override in namespace
    self.namespace["input"] = protocol_input
    self.namespace["__builtins__"]["input"] = protocol_input
```

**Requirements:**
- Token-based request/response correlation
- 30-second default timeout
- Support for concurrent input requests from different operations
- Round-trip latency under 50ms

### State Management

**Source Tracking:**
```python
def _extract_sources(self, tree: ast.AST) -> None:
    """Extract and store function/class definitions from AST."""
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Store function source
            source = ast.unparse(node)
            self._function_sources[node.name] = {
                "source": source,
                "lineno": node.lineno,
                "created_at": time.time()
            }
            
        elif isinstance(node, ast.ClassDef):
            # Store class source
            source = ast.unparse(node)
            self._class_sources[node.name] = {
                "source": source,
                "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)],
                "created_at": time.time()
            }
```

**Checkpoint Creation:**
```python
def create_checkpoint(self) -> bytes:
    """Create comprehensive state checkpoint."""
    
    checkpoint = {
        "version": "1.0",
        "created_at": time.time(),
        "execution_count": self.execution_count,
        "namespace": {},
        "functions": self._function_sources,
        "classes": self._class_sources,
        "imports": self._tracked_imports
    }
    
    # Multi-tier serialization
    for name, obj in self.namespace.items():
        if name.startswith("__"):
            continue
            
        # Try serialization chain
        if cloudpickle:
            try:
                checkpoint["namespace"][name] = {
                    "type": "cloudpickle",
                    "data": base64.b64encode(cloudpickle.dumps(obj)).decode()
                }
                continue
            except:
                pass
                
        if isinstance(obj, (int, float, str, bool, type(None))):
            checkpoint["namespace"][name] = {
                "type": "primitive",
                "data": obj
            }
        elif isinstance(obj, (list, dict, tuple)):
            try:
                json.dumps(obj)  # Verify JSON serializable
                checkpoint["namespace"][name] = {
                    "type": "json",
                    "data": obj
                }
            except:
                pass
    
    # Compress if large
    serialized = msgpack.packb(checkpoint) if msgpack else json.dumps(checkpoint).encode()
    if len(serialized) > 1_000_000:
        return zlib.compress(serialized)
    return serialized
```

### Transaction Support

**Policies:**
- `commit_always`: No snapshot, all changes persist
- `commit_on_success`: Snapshot taken, kept on success
- `rollback_on_failure`: Snapshot taken, restored on exception

**Implementation:**
```python
class TransactionContext:
    def __init__(self, namespace: dict, policy: str):
        self.namespace = namespace
        self.policy = policy
        self.snapshot = None
        
    def __enter__(self):
        if self.policy != "commit_always":
            self.snapshot = copy.deepcopy(self.namespace)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type and self.policy == "rollback_on_failure":
            self.namespace.clear()
            self.namespace.update(self.snapshot)
        return False
```

## Performance Specifications

### Latency Requirements

| Operation | Target | Maximum |
|-----------|--------|---------|
| Simple expression (2+2) | 2ms | 5ms |
| Print to client | 5ms | 10ms |
| Input round-trip | 30ms | 50ms |
| Checkpoint (1MB) | 50ms | 100ms |
| Session acquisition (warm) | 10ms | 100ms |
| Session creation (cold) | 200ms | 500ms |

### Throughput Requirements

| Metric | Target |
|--------|--------|
| Operations per second per session | 1000 |
| Concurrent sessions per manager | 100 |
| Streaming output bandwidth | 10MB/s |
| WebSocket connections per manager | 1000 |
| Pool hit rate after warmup | >80% |

### Resource Limits

| Resource | Per Session | Per Manager |
|----------|------------|-------------|
| Memory | 512MB | 16GB |
| CPU | 1 core | 16 cores |
| File descriptors | 100 | 10,000 |
| Execution timeout | 30s | - |
| Checkpoint size | 10MB | - |

## Critical Implementation Patterns

### Async Synchronization

Use `asyncio.Condition` for protocol framing (not `Event`):
```python
class ProtocolReader:
    def __init__(self):
        self._buffer = bytearray()
        self._condition = asyncio.Condition()
        
    async def read_frame(self) -> bytes:
        async with self._condition:
            # Wait for enough data
            await self._condition.wait_for(lambda: len(self._buffer) >= 4)
            
            # Read length prefix
            length = struct.unpack(">I", self._buffer[:4])[0]
            
            # Wait for complete frame
            await self._condition.wait_for(lambda: len(self._buffer) >= 4 + length)
            
            # Extract frame
            frame = bytes(self._buffer[4:4+length])
            del self._buffer[:4+length]
            
            return frame
```

### Lock-Free Task Creation

Never await while holding locks needed by the awaited tasks:
```python
async def ensure_min_sessions(self):
    tasks = []
    
    # Hold lock only for state inspection
    async with self._lock:
        needed = self.min_idle - len(self._idle)
        if needed > 0:
            # Create tasks but don't await
            for _ in range(needed):
                task = asyncio.create_task(self._create_session())
                tasks.append(task)
    
    # Await outside lock
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # Process results...
```

### Source Preservation

Track source at execution time, not after:
```python
def execute_and_track(self, code: str):
    # Parse BEFORE execution
    tree = ast.parse(code)
    
    # Extract sources BEFORE they exist in namespace
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            self._pending_functions[node.name] = ast.unparse(node)
    
    # Now execute
    exec(compile(tree, "<session>", "exec"), self.namespace)
    
    # Commit tracked sources
    self._function_sources.update(self._pending_functions)
    self._pending_functions.clear()
```

## Error Handling

### Subprocess Crashes
- Monitor process health via `process.poll()`
- Automatic restart on next operation
- Preserve session ID for client transparency
- Log crash details for debugging

### Protocol Violations
- Schema validation on all messages
- Structured error responses
- Never silently drop malformed messages
- Rate limiting on error responses

### Resource Exhaustion
- Monitor memory via `/proc/{pid}/status`
- Graceful degradation when approaching limits
- Clear error messages to clients
- Automatic cleanup of large objects

## Testing Strategy

### Unit Tests
- Protocol message parsing and serialization
- Namespace transaction policies
- Source extraction from AST
- Checkpoint/restore cycles
- Pool acquisition/release logic

### Integration Tests
- End-to-end streaming validation
- Input handling with timeouts
- Session crash recovery
- Concurrent operation handling
- Memory limit enforcement

### Performance Tests
- Latency benchmarks for all operations
- Throughput under sustained load
- Pool efficiency metrics
- Memory usage over time
- Checkpoint size for various workloads

### Compatibility Tests
- WebSocket client compatibility
- REST API compatibility
- Checkpoint format stability
- Protocol version negotiation

## Success Criteria

### Functional Requirements
- [x] Streaming output with <10ms latency
- [x] Interactive input via protocol
- [x] Checkpoint/restore of all state
- [x] Transaction support with rollback
- [x] Session pooling with pre-warming
- [x] Crash recovery without data loss

### Performance Requirements
- [x] 5ms latency for simple operations
- [x] 80% pool hit rate
- [x] 1000 ops/second per session
- [x] <512MB memory per session
- [x] <10MB checkpoint size

### Quality Requirements
- [x] Zero protocol inconsistencies
- [x] No async deadlocks
- [x] No memory leaks over 24 hours
- [x] 99.9% operation success rate
- [x] Graceful degradation under load

## Implementation Phases

### Phase 1: Core Subprocess (Week 1)
- Async execution loop
- Namespace management
- Output streaming
- Basic protocol handler

### Phase 2: Manager and Pool (Week 2)
- Session pool implementation
- Request routing
- Event aggregation
- WebSocket server

### Phase 3: Advanced Features (Week 3)
- Input handling
- Transaction support
- Source tracking
- Checkpoint/restore

### Phase 4: Production Readiness (Week 4)
- Metrics and monitoring
- Error handling
- Performance optimization
- Documentation

### Phase 5: Testing and Validation (Week 5)
- Comprehensive test suite
- Performance benchmarks
- Load testing
- Security audit