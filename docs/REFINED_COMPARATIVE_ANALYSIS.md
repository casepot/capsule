# PyREPL3 Refined Comparative Analysis
## Deep Dive into pyrepl2 and exec-py Architectures

---

## Executive Summary

After deep analysis of both pyrepl2 and exec-py implementations, I've identified the core architectural patterns that make each successful, and precisely where PyREPL3 is falling short. PyREPL3 has the right components but hasn't connected them properly.

### Key Discoveries

1. **Namespace Persistence**: pyrepl2 succeeds because the subprocess lives for the entire session duration
2. **Input Handling**: exec-py succeeds with a one-line fix that PyREPL3 almost implements correctly
3. **Transaction Support**: exec-py's simple snapshot model is elegant and effective
4. **Output Streaming**: Both predecessors use simpler approaches than PyREPL3's over-engineered solution

---

## Part 1: Architecture Recognition

### pyrepl2 Architecture

**Core Philosophy**: "Subprocess as a Service"

```python
# pyrepl2/implementations/base.py:145-156
# Start subprocess (platform-specific)
subprocess = await self._start_subprocess(sandbox_id)

# Create session context
context = SessionContext(
    session_id=session_id,
    sandbox_id=sandbox_id,
    subprocess=subprocess,  # <-- Subprocess lives for session lifetime
    state=SessionState.ACTIVE,
    created_at=datetime.now(UTC),
    execution_count=0,
)
```

**Key Pattern**: SessionContext wraps a long-lived subprocess
- Subprocess created once per session
- Namespace persists naturally because process stays alive
- Clean separation between session management and execution

### exec-py Architecture

**Core Philosophy**: "Event-Driven Execution with Thread Workers"

```python
# exec-py/src/pyrepl/runner_async.py:98-109
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
    ns_snapshot: dict[str, Any] = field(default_factory=dict)  # <-- Snapshot for transactions
    ns: dict[str, Any] = field(default_factory=dict)
```

**Key Pattern**: Operations with namespace snapshots
- Each operation can snapshot and restore namespace
- Thread-based execution with async event delivery
- Clean transaction semantics

### PyREPL3 Architecture

**Current Issue**: Creates new subprocess per Session instance

```python
# pyrepl3/src/session/manager.py:106-114
# Start subprocess
self._process = await asyncio.create_subprocess_exec(
    self._python_path,
    "-m",
    "src.subprocess.worker",
    self.session_id,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

**Problem**: Tests create new Session() for each test, creating new subprocess with fresh namespace

---

## Part 2: Pattern Extraction

### Pattern 1: Subprocess Lifecycle Management

#### pyrepl2 Pattern (ADOPT THIS)
```python
# Subprocess lives for entire session
async def create_session(...) -> Session:
    subprocess = await self._start_subprocess(sandbox_id)
    context = SessionContext(subprocess=subprocess, ...)
    self._sessions[session_id] = context  # Store for reuse
    
async def execute(session_id: SessionId, code: str):
    context = self._get_session_context(session_id)  # Reuse existing
    # Execute on existing subprocess with persistent namespace
```

#### PyREPL3 Fix Required
```python
# Either reuse Session instances OR use SessionPool properly
session = Session()  # Create once
await session.start()

# Multiple executions on SAME session
await session.execute("x = 42")
await session.execute("print(x)")  # Works because same subprocess!
```

### Pattern 2: Input Override Preservation

#### exec-py Pattern (ADOPT THIS)
```python
# exec-py/src/pyrepl/runner_async.py:253
local_ns["input"] = await_input  # Override IN namespace, not just builtins
```

#### PyREPL3 Current Bug
```python
# pyrepl3/src/subprocess/executor.py:159-161, 199
builtins.input = self.create_protocol_input()
self._namespace["input"] = builtins.input  # Sets in namespace
# ... execution ...
builtins.input = original_input  # RESTORES original! Bug!
```

#### Fix Required
```python
def execute_code(self, code: str) -> None:
    # Create protocol input ONCE
    if "input" not in self._namespace or not callable(self._namespace.get("input")):
        protocol_input = self.create_protocol_input()
        self._namespace["input"] = protocol_input  # Permanent override
        
        # Also override in builtins dict if present
        if "__builtins__" in self._namespace:
            if isinstance(self._namespace["__builtins__"], dict):
                self._namespace["__builtins__"]["input"] = protocol_input
            else:
                self._namespace["__builtins__"].input = protocol_input
```

### Pattern 3: Transaction Support

#### exec-py Pattern (ADOPT THIS)
```python
# Snapshot before execution
op.ns_snapshot = {k: v for k, v in self._global_ns.items()}

# Execute with transaction policy
try:
    exec(code, local_ns, local_ns)
    if op.tx_policy == "commit_on_success":
        self._global_ns.update(local_ns)
except Exception:
    if op.tx_policy == "rollback_on_failure":
        self._global_ns.clear()
        self._global_ns.update(op.ns_snapshot)  # Restore snapshot
```

#### PyREPL3 Implementation Required
```python
async def execute_code(self, message: ExecuteMessage):
    # Snapshot for transactions
    if message.transaction_policy != TransactionPolicy.COMMIT_ALWAYS:
        ns_snapshot = dict(self._namespace)
    
    try:
        executor.execute_code(message.code)
        # Handle success based on policy
    except Exception as e:
        if message.transaction_policy == TransactionPolicy.ROLLBACK_ON_FAILURE:
            self._namespace.clear()
            self._namespace.update(ns_snapshot)
        raise
```

### Pattern 4: Output Streaming

#### pyrepl2 Pattern (CONSIDER THIS)
```python
# Simple StringIO capture
stdout_buffer = io.StringIO()
stderr_buffer = io.StringIO()

with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
    exec(code, namespace)

# Send complete output
if stdout_data := stdout_buffer.getvalue():
    send_output(stdout_data, "stdout")
```

#### PyREPL3 Current (OVER-ENGINEERED)
```python
# Complex async output capture with buffering and periodic flushing
class OutputCapture:
    async def write(self, data: str):
        async with self._lock:
            self._buffer.write(data)
            if not self._flush_task:
                self._flush_task = asyncio.create_task(self._flush_periodic())
```

---

## Part 3: Convergence and Divergence Points

### Where to Converge with pyrepl2

1. **Session Persistence Model** ✅ MUST ADOPT
   - Keep subprocess alive for session duration
   - Store SessionContext for reuse
   - Only terminate on explicit shutdown

2. **Checkpoint with Source Code** ✅ ADOPT
   - Extract function/class sources during execution
   - Store in checkpoint for full restoration
   - Multi-tier serialization (cloudpickle → msgpack → JSON)

3. **Session Pool Pattern** ✅ ALREADY HAVE
   - PyREPL3 has SessionPool, just needs proper usage
   - Pre-warm sessions for instant availability
   - Reuse sessions across requests

### Where to Converge with exec-py

1. **Input Override Pattern** ✅ MUST ADOPT
   - Override input IN namespace permanently
   - Don't restore original after execution
   - Simple one-line fix: `local_ns["input"] = protocol_input`

2. **Transaction Model** ✅ ADOPT
   - Snapshot namespace before execution
   - Apply transaction policy on success/failure
   - Simple dict copy is sufficient

3. **FD Separation** 🔄 CONSIDER
   - exec-py v0.2 successfully separated protocol FDs
   - Frees stdin/stdout for user code
   - Clean separation of concerns

### Where PyREPL3 Should Diverge/Improve

1. **Simplified Output Streaming** 🚀 IMPROVE
   - Current async buffering is over-complex
   - Consider pyrepl2's StringIO approach
   - Or exec-py's direct streaming without buffering

2. **Unified Message Protocol** ✅ KEEP
   - PyREPL3's strongly-typed messages are good
   - Better than exec-py's TypedDict approach
   - More structured than pyrepl2's JSON-RPC

3. **Thread-Safe Execution** ✅ KEEP
   - ThreadedExecutor pattern is solid
   - Handles blocking I/O well
   - Just needs namespace persistence fix

---

## Part 4: Root Cause Analysis

### Why Namespace Persistence Fails

1. **Test Pattern Issue**
```python
# WRONG: Each test creates new Session
async def test_1():
    session = Session()  # New subprocess!
    await session.start()
    
async def test_2():
    session = Session()  # Another new subprocess!
    await session.start()
```

2. **Correct Pattern**
```python
# RIGHT: Reuse session
session = Session()
await session.start()

# Multiple operations on same session
await session.execute("x = 42")
result = await session.execute("x * 2")  # Works!
```

### Why Input Override Fails

**Current Bug in executor.py:199**
```python
finally:
    builtins.input = original_input  # BUG: Restores original!
```

**Fix**: Don't restore, keep override in namespace permanently

### Why Transactions Don't Work

**Not Implemented**: Message definitions exist but no handler implementation

---

## Part 5: Implementation Priority

### Priority 1: Critical Fixes (Week 1)

1. **Fix Namespace Persistence**
   - Update tests to reuse Session instances
   - OR properly use SessionPool.acquire()/release()
   - Document the pattern clearly

2. **Fix Input Override**
   - Remove `builtins.input = original_input` restoration
   - Ensure input override persists in namespace
   - Test across multiple executions

### Priority 2: Feature Completion (Week 2)

3. **Implement Transactions**
   - Add namespace snapshot before execution
   - Implement rollback on failure
   - Test all transaction policies

4. **Implement Checkpoints**
   - Extract source during execution (like pyrepl2)
   - Implement checkpoint/restore handlers
   - Add multi-tier serialization

### Priority 3: Architecture Improvements (Week 3)

5. **Simplify Output Streaming**
   - Consider StringIO approach
   - Or simplify current async implementation
   - Benchmark and choose best approach

6. **Consider FD Separation**
   - Review exec-py v0.2 implementation
   - Evaluate benefit vs complexity
   - Implement if worthwhile

---

## Conclusion

PyREPL3 has solid architecture but needs to connect the pieces properly:

1. **pyrepl2 teaches us**: Keep subprocess alive for session duration
2. **exec-py teaches us**: Simple namespace overrides and snapshots work
3. **PyREPL3's strength**: Good message protocol and threading model

The fixes are straightforward because the architecture is sound. With these targeted changes, PyREPL3 will achieve its vision of being a production-ready execution service that combines the best of both predecessors.

## Code Examples from Deep Dive

### pyrepl2's Session Persistence
```python
# pyrepl2/pyrepl2/implementations/base.py:145-172
# Subprocess created once, stored in context
context = SessionContext(
    session_id=session_id,
    sandbox_id=sandbox_id,
    subprocess=subprocess,  # Lives for session lifetime
    state=SessionState.ACTIVE,
    created_at=datetime.now(UTC),
    execution_count=0,
)
self._sessions[session_id] = context  # Stored for reuse
```

### exec-py's Transaction Implementation
```python
# exec-py/src/pyrepl/runner_async.py:258-270
if op.tx_policy == "commit_on_success":
    self._global_ns.update(local_ns)
elif op.tx_policy == "rollback_on_failure":
    self._global_ns.update(local_ns)  # success => commit
# ... on exception ...
if op.tx_policy in ("rollback_on_failure", "explicit"):
    op.ns = {k: v for k, v in op.ns_snapshot.items()}  # restore
```

### PyREPL3's Current Issues
```python
# pyrepl3/src/subprocess/executor.py:159-199
builtins.input = self.create_protocol_input()
self._namespace["input"] = builtins.input  # Good!
# ... execution ...
builtins.input = original_input  # BAD! Removes override!
```

The path forward is clear: adopt the proven patterns from both predecessors while maintaining PyREPL3's cleaner architecture.