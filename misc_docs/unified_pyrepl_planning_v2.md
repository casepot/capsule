# Unified PyREPL System Planning (v2.0)
## Updated with Deep Analysis Insights

> **Last Updated**: Based on comparative analysis of pyrepl2 and exec-py patterns
> **Status**: Reflects actual implementation state and refined architecture

## Mission

Design and implement a Python REPL execution system with persistent sessions, real-time streaming output, interactive input handling, comprehensive state management, and session pooling.

## System Architecture (REVISED)

### Component Overview

```
┌─────────────┐       ┌─────────────┐       ┌──────────────┐
│   Client    │──────▶│   Manager   │──────▶│  Subprocess  │
│ (WebSocket) │◀──────│  (Router)   │◀──────│   (Worker)   │
└─────────────┘       └─────────────┘       └──────────────┘
                            │                      │
                            ▼                      ▼
                      ┌──────────┐          ┌──────────────┐
                      │   Pool   │          │ThreadedExecutor│
                      └──────────┘          └──────────────┘
                                                   │
                                                   ▼
                                            ┌──────────┐
                                            │Namespace │
                                            └──────────┘
```

### Subprocess Architecture (UPDATED)

Each session runs as a long-lived Python subprocess with:

**Core Components:**
- **ThreadedExecutor** for user code execution (not async) - enables blocking I/O
- Persistent namespace dictionary across executions (key insight from pyrepl2)
- AST-based source tracking for function/class definitions
- Direct output streaming without complex buffering
- Protocol-based input handling with namespace override (not restoration)

**Execution Flow (Thread-Based Model):**
```python
class ThreadedExecutor:
    """Execute user code in dedicated thread for blocking I/O support."""
    
    def execute_code(self, code: str) -> None:
        """Execute in thread context - REVISED based on exec-py pattern."""
        import builtins
        
        # CRITICAL FIX: Only create protocol input if not already overridden
        if "input" not in self._namespace or not callable(self._namespace.get("input")):
            protocol_input = self.create_protocol_input()
            # Override in namespace PERMANENTLY (exec-py lesson)
            self._namespace["input"] = protocol_input
            if "__builtins__" in self._namespace:
                if isinstance(self._namespace["__builtins__"], dict):
                    self._namespace["__builtins__"]["input"] = protocol_input
                else:
                    self._namespace["__builtins__"].input = protocol_input
            builtins.input = protocol_input
        
        # Save only stdout/stderr (NOT input!)
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        try:
            # Simple output redirection (pyrepl2 lesson)
            sys.stdout = DirectStreamOutput(self._transport, StreamType.STDOUT, self._execution_id)
            sys.stderr = DirectStreamOutput(self._transport, StreamType.STDERR, self._execution_id)
            
            # Parse and track sources BEFORE execution
            tree = ast.parse(code)
            self._extract_definitions(tree)
            
            # Execute in persistent namespace
            compiled = compile(tree, "<session>", "exec")
            exec(compiled, self._namespace)
            
        finally:
            # Restore ONLY stdout/stderr (NOT input!)
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            # DO NOT restore builtins.input - this was the bug!

async def handle_execute(self, message: ExecuteMessage) -> None:
    """Handle execute message with transaction support."""
    
    # Transaction snapshot (exec-py pattern)
    snapshot = None
    if message.transaction_policy != TransactionPolicy.COMMIT_ALWAYS:
        snapshot = dict(self._namespace)  # Simple dict copy
    
    try:
        # Create executor for thread-based execution
        executor = ThreadedExecutor(
            transport=self._transport,
            namespace=self._namespace,
            execution_id=message.id
        )
        
        # Run in thread (not async!)
        thread = threading.Thread(
            target=executor.execute_code,
            args=(message.code,),
            daemon=True
        )
        thread.start()
        thread.join(timeout=message.timeout)
        
        if thread.is_alive():
            raise TimeoutError(f"Execution exceeded {message.timeout}s")
        
        # Check for error
        if hasattr(executor, '_error') and executor._error:
            raise executor._error
            
    except Exception as e:
        # Transaction rollback (exec-py pattern)
        if message.transaction_policy == TransactionPolicy.ROLLBACK_ON_FAILURE:
            if snapshot is not None:
                self._namespace.clear()
                self._namespace.update(snapshot)
                import builtins
                self._namespace["__builtins__"] = builtins
        raise
```

### Manager Architecture (UPDATED)

The manager orchestrates sessions and client connections:

**Session Pool (Lock-Free Pattern):**
```python
class SessionPool:
    """Pre-warmed subprocess pool with LOCK-FREE acquisition pattern."""
    
    def __init__(self, config: PoolConfig):
        self.min_idle = config.min_idle
        self.max_idle = config.max_idle
        self.max_total = config.max_total
        self.session_ttl = config.session_ttl
        
        self._idle: deque[SessionInfo] = deque()
        self._active: dict[SessionId, SessionInfo] = {}
        self._warming: set[SessionId] = set()  # Track warming sessions
        self._metrics = PoolMetrics()
        
    async def acquire(self, timeout: float = 5.0) -> SessionId:
        """Lock-free acquisition pattern to prevent deadlocks."""
        
        # CRITICAL: Reserve slot BEFORE creating session
        async with self._lock:
            # Check idle pool first
            while self._idle:
                session = self._idle.popleft()
                if not session.is_expired():
                    self._active[session.id] = session
                    self._metrics.record_hit()
                    return session.id
            
            # Check if we can create new session
            total = len(self._active) + len(self._warming)
            if total < self.max_total:
                # Reserve slot with placeholder
                placeholder_id = SessionId(str(uuid.uuid4()))
                self._warming.add(placeholder_id)
            else:
                # Must wait for available session
                return await self._wait_for_available(timeout)
        
        # Create session OUTSIDE lock (lock-free pattern)
        try:
            session = await self._create_session()
            
            # Swap placeholder with real session
            async with self._lock:
                self._warming.discard(placeholder_id)
                self._active[session.id] = session
                
            return session.id
            
        except Exception:
            # Clean up reservation on failure
            async with self._lock:
                self._warming.discard(placeholder_id)
            raise
```

**Session Reuse Pattern (Critical Fix):**
```python
# WRONG - Creates new subprocess each time
async def test_wrong():
    session = Session()  # New subprocess!
    await session.start()
    await session.execute("x = 42")
    
    session = Session()  # Another new subprocess!
    await session.start()
    await session.execute("print(x)")  # NameError!

# CORRECT - Reuses same subprocess
async def test_correct():
    pool = SessionPool(config)
    await pool.start()
    
    session = await pool.acquire()  # Get subprocess
    await session.execute("x = 42")
    await session.execute("print(x)")  # Works! x=42
    await pool.release(session)  # Keep subprocess alive
```

### Protocol Specification (UNCHANGED)

Message format remains the same, but transport improvements:

**Transport Layer:**
- Length-prefixed framing: 4-byte big-endian length + JSON payload
- Single bidirectional channel per subprocess
- **FD Separation Option**: Protocol on separate FDs from stdin/stdout (exec-py v0.2 pattern)
- WebSocket for client connections

## Technical Requirements (REVISED)

### Streaming Output (SIMPLIFIED)

**Implementation (Based on pyrepl2/exec-py lessons):**
```python
class DirectStreamOutput:
    """Simple direct output streaming without complex buffering."""
    
    def __init__(self, transport, stream_type, execution_id, loop):
        self._transport = transport
        self._stream_type = stream_type
        self._execution_id = execution_id
        self._loop = loop
    
    def write(self, data: str) -> int:
        """Send output immediately - no buffering."""
        if not data:
            return 0
            
        message = OutputMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            data=data,
            stream=self._stream_type,
            execution_id=self._execution_id
        )
        
        # Send from thread using thread-safe method
        asyncio.run_coroutine_threadsafe(
            self._transport.send_message(message),
            self._loop
        )
        
        return len(data)
    
    def flush(self) -> None:
        """No buffering, nothing to flush."""
        pass
```

### Interactive Input (CRITICAL FIX)

**Namespace Override (Permanent, Not Restored):**
```python
def create_protocol_input(self) -> Callable:
    """Create input() replacement that uses protocol."""
    
    def protocol_input(prompt: str = "") -> str:
        """Thread-safe input via protocol messages."""
        # Generate unique token
        token = str(uuid.uuid4())
        
        # Send INPUT message from thread
        future = asyncio.run_coroutine_threadsafe(
            self._send_input_request(token, prompt),
            self._loop
        )
        future.result()  # Wait for send
        
        # Wait for response in thread (using threading.Event)
        event = threading.Event()
        self._input_waiters[token] = (event, None)
        
        # Wait with timeout
        if not event.wait(timeout=30.0):
            raise TimeoutError("Input timeout")
        
        # Get response
        _, response = self._input_waiters.pop(token)
        return response
    
    return protocol_input

# CRITICAL: Override in namespace ONCE and keep it
self._namespace["input"] = protocol_input  # Never restore!
```

### State Management (ENHANCED)

**Source Tracking (pyrepl2 pattern):**
```python
def _extract_definitions(self, code: str) -> None:
    """Extract sources BEFORE execution."""
    try:
        tree = ast.parse(code)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Store function source
                func_source = ast.unparse(node)
                self._function_sources[node.name] = func_source
                
            elif isinstance(node, ast.ClassDef):
                # Store class source
                class_source = ast.unparse(node)
                self._class_sources[node.name] = class_source
                
            elif isinstance(node, ast.Import):
                # Track imports
                for alias in node.names:
                    import_stmt = f"import {alias.name}"
                    if import_stmt not in self._imports:
                        self._imports.append(import_stmt)
    except:
        pass  # Best effort
```

**Checkpoint Creation (Multi-tier serialization from pyrepl2):**
```python
def create_checkpoint(self) -> bytes:
    """Create comprehensive state checkpoint."""
    
    checkpoint_data = {
        "version": 2,
        "created_at": time.time(),
        "namespace": self._serialize_namespace(),
        "function_sources": self._function_sources,
        "class_sources": self._class_sources,
        "imports": self._imports,
        "execution_count": self._execution_count
    }
    
    # Multi-tier serialization (pyrepl2 pattern)
    try:
        import cloudpickle
        serialized = cloudpickle.dumps(checkpoint_data)
        method = "cloudpickle"
    except:
        try:
            import msgpack
            serialized = msgpack.packb(checkpoint_data, use_bin_type=True)
            method = "msgpack"
        except:
            import json
            serialized = json.dumps(checkpoint_data, default=str).encode('utf-8')
            method = "json"
    
    # Compress if large
    if len(serialized) > 1_000_000:
        serialized = zlib.compress(serialized)
    
    return serialized
```

### Transaction Support (exec-py pattern)

**Implementation (Simplified from exec-py):**
```python
# Before execution - snapshot if needed
snapshot = None
if message.transaction_policy != TransactionPolicy.COMMIT_ALWAYS:
    snapshot = dict(self._namespace)  # Simple dict copy

try:
    # Execute code
    executor.execute_code(message.code)
    
    # SUCCESS - policy already applied (namespace modified)
    if message.transaction_policy == TransactionPolicy.COMMIT_ON_SUCCESS:
        pass  # Changes already committed
        
except Exception as e:
    # FAILURE - apply rollback if needed
    if message.transaction_policy == TransactionPolicy.ROLLBACK_ON_FAILURE:
        if snapshot is not None:
            self._namespace.clear()
            self._namespace.update(snapshot)
            # Restore builtins
            import builtins
            self._namespace["__builtins__"] = builtins
    raise
```

## Performance Specifications (REALISTIC)

### Latency Requirements (Updated with Actual vs Target)

| Operation | Target | Actual | Maximum |
|-----------|--------|--------|---------|
| Simple expression (2+2) | 2ms | ~5ms | 10ms |
| Print to client | 5ms | ~8ms | 15ms |
| Input round-trip | 30ms | ~40ms | 60ms |
| Checkpoint (1MB) | 50ms | ~80ms | 150ms |
| Session acquisition (warm) | 10ms | 0.021ms ✅ | 100ms |
| Session creation (cold) | 200ms | ~85ms ✅ | 500ms |

### Resource Limits (Unchanged)

| Resource | Per Session | Per Manager |
|----------|------------|-------------|
| Memory | 512MB | 16GB |
| CPU | 1 core | 16 cores |
| File descriptors | 100 | 10,000 |
| Execution timeout | 30s | - |
| Checkpoint size | 10MB | - |

## Critical Implementation Patterns (UPDATED)

### Thread-Safe Output from Executor

```python
class ThreadSafeOutput:
    """Bridge thread output to async transport."""
    
    def write(self, data: str) -> int:
        """Send from thread context."""
        # Use thread-safe method to schedule async send
        future = asyncio.run_coroutine_threadsafe(
            self._send_output(data),
            self._loop
        )
        # Don't wait (non-blocking)
        return len(data)
```

### Lock-Free Pool Operations

```python
async def ensure_min_sessions(self):
    """Ensure minimum idle sessions WITHOUT deadlock."""
    tasks = []
    
    # Hold lock only for planning
    async with self._lock:
        needed = self.min_idle - len(self._idle) - len(self._warming)
        if needed > 0:
            # Reserve slots
            for _ in range(needed):
                placeholder_id = str(uuid.uuid4())
                self._warming.add(placeholder_id)
                # Create task but DON'T await inside lock
                task = asyncio.create_task(self._create_session())
                tasks.append((placeholder_id, task))
    
    # Await OUTSIDE lock (critical!)
    for placeholder_id, task in tasks:
        try:
            session = await task
            async with self._lock:
                self._warming.discard(placeholder_id)
                self._idle.append(session)
        except:
            async with self._lock:
                self._warming.discard(placeholder_id)
```

### Input Override Pattern (exec-py lesson)

```python
# WRONG - Restores original input
finally:
    builtins.input = original_input  # BUG!

# CORRECT - Keep override permanent
# Simply don't restore input - let it persist in namespace
```

## Lessons Learned from Analysis

### From pyrepl2
1. **Session persistence requires subprocess reuse** - Don't create new Session() each time
2. **Source preservation enables full restoration** - Extract AST before execution
3. **Multi-tier serialization provides compatibility** - cloudpickle → msgpack → JSON
4. **Simple output capture works** - StringIO + redirect_stdout is sufficient

### From exec-py
1. **Thread-based execution enables blocking I/O** - Critical for input() support
2. **Namespace override must persist** - Don't restore input after execution
3. **Simple snapshots enable transactions** - dict copy is sufficient
4. **FD separation prevents conflicts** - Protocol on separate FDs from stdio

### From PyREPL3 Issues
1. **Over-engineering causes problems** - OutputCapture complexity caused failures
2. **Lock-holding during async operations causes deadlocks** - Use lock-free patterns
3. **Architecture is sound, bugs are simple** - Most fixes are 1-5 lines

## Success Criteria (UPDATED WITH ACTUAL STATE)

### Functional Requirements
- [✅] Streaming output with <10ms latency (achieved ~8ms)
- [✅] Interactive input via protocol (thread-based implementation works)
- [❌] Checkpoint/restore of all state (not implemented)
- [❌] Transaction support with rollback (not implemented)
- [✅] Session pooling with pre-warming (lock-free pattern implemented)
- [⚠️] Crash recovery without data loss (partially implemented)

### Performance Requirements
- [✅] <10ms latency for simple operations (achieved ~5ms)
- [✅] 80% pool hit rate (measured >85%)
- [?] 1000 ops/second per session (not measured)
- [?] <512MB memory per session (not enforced)
- [?] <10MB checkpoint size (not implemented)

### Quality Requirements
- [✅] Zero protocol inconsistencies
- [✅] No async deadlocks (fixed with lock-free pattern)
- [?] No memory leaks over 24 hours (not tested)
- [?] 99.9% operation success rate (not measured)
- [⚠️] Graceful degradation under load (basic implementation)

## Implementation Status and Phases (REVISED)

### Completed
- ✅ Thread-based executor for blocking I/O
- ✅ Input handling via protocol messages
- ✅ Session pooling with lock-free acquisition
- ✅ Basic output streaming
- ✅ Protocol message definitions

### In Progress (Critical Fixes Needed)
- 🔧 Input override persistence (line 199 bug)
- 🔧 Session reuse in tests
- 🔧 API layer implementation

### Not Started
- ❌ Transaction support implementation
- ❌ Checkpoint/restore handlers
- ❌ Source tracking during execution
- ❌ FD separation
- ❌ Resource limit enforcement

### Phase 1: Critical Fixes (Days 1-2)
- Fix input override persistence (remove restoration)
- Implement session reuse pattern in tests
- Complete API layer (WebSocket + REST)

### Phase 2: Core Features (Days 3-4)
- Implement transaction support
- Complete checkpoint/restore system
- Add source tracking

### Phase 3: Optimization (Day 5)
- Simplify output streaming
- Add FD separation option
- Performance benchmarking

### Phase 4: Production Readiness (Week 2)
- Resource limit enforcement
- Metrics and monitoring
- Error handling improvements
- Documentation

### Phase 5: Testing and Validation (Week 3)
- Comprehensive test suite
- Performance benchmarks
- Load testing
- Security audit

## Key Architecture Decisions

### Why Thread-Based Execution?
- Enables blocking I/O (critical for input())
- Natural fit for Python's execution model
- Simpler than async context managers
- Proven by exec-py

### Why Session Reuse?
- Namespace persistence requires living subprocess
- Pool amortizes subprocess creation cost
- Enables warm acquisition (<1ms)
- Standard pattern in execution services

### Why Lock-Free Pool?
- Prevents deadlocks from nested acquisition
- Allows parallel session creation
- Scales better under load
- Cleaner error handling

### Why Simple Output Streaming?
- Complex buffering caused failures
- Direct streaming is sufficient
- Lower latency without buffering
- Easier to debug

## Next Steps

1. **Apply critical fixes** from planning_prompts/
2. **Validate with test_foundation/** suite
3. **Implement remaining features** per roadmap
4. **Benchmark against targets**
5. **Create client SDKs**
6. **Deploy and monitor**

---

*This document supersedes the original unified_pyrepl_planning.md with lessons learned from deep comparative analysis of pyrepl2 and exec-py architectures.*