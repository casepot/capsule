# PyREPL3 Actionable Fixes
## Based on Comparative Analysis with pyrepl2 & exec-py

---

## Priority 1: Critical Fixes (Blocking Issues)

### Fix 1: Namespace Persistence
**Problem**: Variables don't persist between executions because tests create new Session instances
**Root Cause**: Each `Session()` creates a new subprocess with fresh namespace
**Evidence**: pyrepl2 keeps subprocess alive for session duration

#### Solution A: Singleton Session Pattern (Quick Fix)
```python
# In test files, reuse same session
async def test_persistence():
    session = Session()  # Create once
    await session.start()
    
    # First execution
    await session.execute("x = 42")
    
    # Second execution - SAME session
    result = await session.execute("print(x)")  # Should work
    
    await session.shutdown()  # Only at end
```

#### Solution B: Session Pool Integration (Better)
```python
# Use existing SessionPool to maintain persistent sessions
pool = SessionPool(config)
session = await pool.acquire()  # Reuses existing subprocess

# Multiple executions on same session
await session.execute("x = 1")
await session.execute("print(x)")  # Works!

await pool.release(session)  # Returns to pool, keeps alive
```

### Fix 2: Input Override in Namespace
**Problem**: Input override not preserved between executions
**Root Cause**: Not following exec-py's namespace pattern
**Evidence**: exec-py line 253: `local_ns["input"] = await_input`

#### Implementation:
```python
# In executor.py execute_code() method
def execute_code(self, code: str) -> None:
    import builtins
    
    # Create protocol input
    protocol_input = self.create_protocol_input()
    
    # Override in namespace (not just globally!)
    self._namespace["input"] = protocol_input
    if "__builtins__" in self._namespace:
        if isinstance(self._namespace["__builtins__"], dict):
            self._namespace["__builtins__"]["input"] = protocol_input
        else:
            self._namespace["__builtins__"].input = protocol_input
    
    # NOW execute with properly configured namespace
    exec(compile(code, "<session>", "exec"), self._namespace, self._namespace)
```

### Fix 3: Simplify Output Streaming
**Problem**: Complex async output capture causes reliability issues
**Root Cause**: Over-engineered async/thread bridging
**Evidence**: pyrepl2 uses simple StringIO capture

#### Solution: Buffer-and-Send Pattern
```python
# Replace complex OutputCapture with simple approach
def execute_code(self, code: str) -> None:
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exec(compile(code, "<session>", "exec"), self._namespace)
    
    # Send complete output after execution
    if stdout_data := stdout_buffer.getvalue():
        self.send_output(stdout_data, StreamType.STDOUT)
    if stderr_data := stderr_buffer.getvalue():
        self.send_output(stderr_data, StreamType.STDERR)
```

---

## Priority 2: Feature Completion

### Fix 4: Transaction Support
**Problem**: Transaction policies defined but not implemented
**Evidence**: exec-py has full implementation with namespace snapshots

#### Implementation:
```python
# In worker.py execute_code method
async def execute_code(self, message: ExecuteMessage):
    # Snapshot for transactions
    if message.transaction_policy != TransactionPolicy.COMMIT_ALWAYS:
        ns_snapshot = dict(self._namespace)
    
    try:
        # Execute code
        executor.execute_code(message.code)
        
        # Success - commit or explicit
        if message.transaction_policy == TransactionPolicy.COMMIT_ON_SUCCESS:
            pass  # Keep changes
        elif message.transaction_policy == TransactionPolicy.EXPLICIT:
            pass  # Keep changes but mark for review
            
    except Exception as e:
        # Failure - rollback if needed
        if message.transaction_policy == TransactionPolicy.ROLLBACK_ON_FAILURE:
            self._namespace.clear()
            self._namespace.update(ns_snapshot)
        raise
```

### Fix 5: Checkpoint/Restore
**Problem**: Messages exist but handlers not implemented
**Evidence**: pyrepl2 has full serialization chain

#### Implementation:
```python
# In worker.py
async def handle_checkpoint(self, message: CheckpointMessage):
    checkpoint_data = {
        "namespace": self._serialize_namespace(),
        "function_sources": self._function_sources,
        "class_sources": self._class_sources,
        "imports": self._imports,
        "execution_count": self._execution_count
    }
    
    # Multi-tier serialization (from pyrepl2)
    try:
        import cloudpickle
        data = cloudpickle.dumps(checkpoint_data)
    except:
        import pickle
        data = pickle.dumps(checkpoint_data)
    
    # Send checkpoint response
    response = CheckpointCreatedMessage(
        checkpoint_id=str(uuid.uuid4()),
        data=data,
        size_bytes=len(data)
    )
    await self._transport.send_message(response)

def _serialize_namespace(self):
    """Serialize namespace safely."""
    safe_ns = {}
    for name, obj in self._namespace.items():
        if name.startswith("__"):
            continue
        try:
            # Test serializability
            import pickle
            pickle.dumps(obj)
            safe_ns[name] = obj
        except:
            # Skip non-serializable
            pass
    return safe_ns
```

---

## Priority 3: Architecture Improvements

### Fix 6: FD Separation (Optional but Clean)
**Problem**: Protocol uses stdin/stdout, blocking user code
**Evidence**: exec-py v0.2 successfully separated FDs

#### Implementation:
```python
# In manager.py when creating subprocess
import os

# Create pipes for protocol
to_runner_r, to_runner_w = os.pipe()
from_runner_r, from_runner_w = os.pipe()

# Pass FD numbers via environment
env = os.environ.copy()
env['PYREPL_PROTOCOL_FDS'] = f'{to_runner_r},{from_runner_w}'

# Create subprocess with FDs
process = await asyncio.create_subprocess_exec(
    sys.executable, "-m", "src.subprocess.worker",
    stdin=asyncio.subprocess.PIPE,  # Now free for user
    stdout=asyncio.subprocess.PIPE,  # Now free for user
    stderr=asyncio.subprocess.PIPE,
    pass_fds=(to_runner_r, from_runner_w),
    env=env
)
```

### Fix 7: Unified Execution Model
**Problem**: Complex ThreadedExecutor + async transport
**Evidence**: Both predecessors use simpler models

#### Option A: Follow pyrepl2 (Simpler)
- Execute synchronously in subprocess
- Capture output to buffer
- Send complete results

#### Option B: Follow exec-py (More Features)
- Thread per operation
- Namespace copies for transactions
- Thread-safe event emission

---

## Testing Strategy

### Test Namespace Persistence
```python
async def test_namespace_persistence_fixed():
    """Verify namespace persists across executions."""
    session = Session()
    await session.start()
    
    # Define variable
    await session.execute("x = 42")
    
    # Use in next execution
    result = await session.execute("x * 2")
    assert result.value == 84
    
    # Define function
    await session.execute("def greet(name): return f'Hello {name}'")
    
    # Use function
    result = await session.execute("greet('World')")
    assert result.value == "Hello World"
    
    await session.shutdown()
```

### Test Input Handling
```python
async def test_input_persistence():
    """Verify input() works across executions."""
    session = Session()
    await session.start()
    
    # First execution with input
    code1 = "name = input('Name: ')"
    async for msg in session.execute(code1):
        if msg.type == MessageType.INPUT:
            await session.input_response(msg.id, "Alice")
    
    # Second execution uses variable from input
    result = await session.execute("f'Hello {name}'")
    assert result.value == "Hello Alice"
    
    await session.shutdown()
```

---

## Implementation Order

1. **Week 1**: Fix namespace persistence (Priority 1)
   - Update tests to reuse sessions
   - Or integrate SessionPool properly

2. **Week 2**: Fix input and output (Priority 1)
   - Implement namespace input override
   - Simplify output streaming

3. **Week 3**: Add transactions and checkpoints (Priority 2)
   - Copy patterns from exec-py/pyrepl2
   - Add tests

4. **Week 4**: Architecture cleanup (Priority 3)
   - Consider FD separation
   - Simplify execution model

---

## Success Metrics

| Metric | Current | Target | Test |
|--------|---------|--------|------|
| Namespace persistence | ❌ Fails | ✅ Works | Variables available |
| Class persistence | ❌ Fails | ✅ Works | Classes instantiable |
| Import persistence | ⚠️ Partial | ✅ Works | Modules available |
| Input handling | ✅ Works once | ✅ Works always | input() reliable |
| Output streaming | ⚠️ Unreliable | ✅ Reliable | All output captured |
| Transactions | ❌ Not implemented | ✅ Works | Rollback on error |
| Checkpoints | ❌ Not implemented | ✅ Works | State saveable |

---

## Key Insights from Analysis

1. **pyrepl2's Strength**: Simple, persistent subprocess with clear namespace
2. **exec-py's Strength**: Elegant input handling and transaction support
3. **PyREPL3's Issue**: Has the pieces but didn't connect them properly

The fixes are straightforward because the architecture is sound. We just need to:
- Keep subprocesses alive (like pyrepl2)
- Override input properly (like exec-py)
- Simplify where we over-engineered

With these changes, PyREPL3 will achieve its vision of being a production-ready execution service.