# PyREPL3 Refined Actionable Fixes
## Based on Deep Code Analysis of pyrepl2 & exec-py

---

## Critical Discovery

After deep analysis, I found that **PyREPL3's architecture is fundamentally sound** but has three critical bugs that break core functionality. These are simple fixes that will immediately restore expected behavior.

---

## Bug Fix 1: Input Override Not Persisting

### The Bug
**Location**: `/src/subprocess/executor.py:199`

```python
# CURRENT CODE (BROKEN)
def execute_code(self, code: str) -> None:
    import builtins
    original_input = builtins.input  # Save original
    try:
        builtins.input = self.create_protocol_input()
        self._namespace["input"] = builtins.input
        # ... execution ...
    finally:
        builtins.input = original_input  # BUG: RESTORES ORIGINAL!
```

### The Fix
**Remove the restoration of original input**:

```python
# FIXED CODE
def execute_code(self, code: str) -> None:
    import builtins
    
    # Only create protocol input if not already overridden
    if "input" not in self._namespace or not callable(self._namespace.get("input")):
        protocol_input = self.create_protocol_input()
        
        # Override in namespace permanently (like exec-py line 253)
        self._namespace["input"] = protocol_input
        
        # Also override in builtins for this namespace
        if "__builtins__" in self._namespace:
            if isinstance(self._namespace["__builtins__"], dict):
                self._namespace["__builtins__"]["input"] = protocol_input
            else:
                self._namespace["__builtins__"].input = protocol_input
        
        # Override global builtins for exec context
        builtins.input = protocol_input
    
    # Save stdout/stderr originals (these we DO restore)
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    try:
        # Redirect output streams
        sys.stdout = ThreadSafeOutput(self, StreamType.STDOUT)
        sys.stderr = ThreadSafeOutput(self, StreamType.STDERR)
        
        # Execute code
        compiled = compile(code, "<session>", "exec")
        exec(compiled, self._namespace)
        
    finally:
        # Restore ONLY stdout/stderr (NOT input!)
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        # DO NOT restore builtins.input!
```

**Evidence from exec-py**:
```python
# exec-py/src/pyrepl/runner_async.py:253
local_ns["input"] = await_input  # They override IN namespace and keep it
```

---

## Bug Fix 2: Session Reuse Pattern

### The Bug
**Issue**: Tests create new Session() instances, creating new subprocesses with fresh namespaces

### The Fix

#### Option A: Update Test Pattern (Quick)
```python
# test_foundation/test_namespace_and_transactions.py

# Add session fixture
@pytest.fixture
async def persistent_session():
    """Create a single session for all tests in a class."""
    session = Session()
    await session.start()
    yield session
    await session.shutdown()

# Use fixture in tests
async def test_namespace_persistence(persistent_session):
    session = persistent_session  # Reuse existing session
    
    # First execution
    await session.execute("x = 42")
    
    # Second execution - namespace persists!
    result = await session.execute("x * 2")
    assert result.value == 84
```

#### Option B: Use SessionPool Properly (Better)
```python
# test_foundation/test_namespace_and_transactions.py

# Create pool fixture
@pytest.fixture
async def session_pool():
    """Create session pool for tests."""
    config = PoolConfig(min_idle_sessions=1, max_sessions=5)
    pool = SessionPool(config)
    await pool.start()
    yield pool
    await pool.shutdown()

# Use pool in tests
async def test_namespace_persistence(session_pool):
    # Acquire session from pool
    session = await session_pool.acquire()
    
    try:
        # First execution
        await session.execute("x = 42")
        
        # Second execution - same session, namespace persists!
        result = await session.execute("x * 2")
        assert result.value == 84
        
    finally:
        # Release back to pool (keeps subprocess alive)
        await session_pool.release(session)
```

**Evidence from pyrepl2**:
```python
# pyrepl2/implementations/base.py:172
self._sessions[session_id] = context  # They store and reuse sessions
```

---

## Bug Fix 3: Transaction Implementation

### The Bug
**Issue**: Transaction handlers not implemented despite message definitions

### The Fix
**Location**: `/src/subprocess/worker.py`, add to `handle_execute` method:

```python
async def handle_execute(self, message: ExecuteMessage) -> None:
    """Handle execute message with transaction support."""
    
    # Snapshot namespace if transaction policy requires it
    ns_snapshot = None
    if message.transaction_policy != TransactionPolicy.COMMIT_ALWAYS:
        # Deep copy namespace for potential rollback (like exec-py)
        ns_snapshot = dict(self._namespace)
    
    try:
        # Create executor
        executor = ThreadedExecutor(
            transport=self._transport,
            namespace=self._namespace,
            execution_id=message.id,
        )
        
        # Run execution in thread
        thread = threading.Thread(
            target=executor.execute_code,
            args=(message.code,),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=message.timeout)
        
        if thread.is_alive():
            # Handle timeout
            raise TimeoutError(f"Execution exceeded {message.timeout}s")
        
        # Check for execution error
        if hasattr(executor, '_error') and executor._error:
            raise executor._error
        
        # SUCCESS PATH - Apply transaction policy
        if message.transaction_policy == TransactionPolicy.COMMIT_ON_SUCCESS:
            # Changes already in namespace, nothing to do
            pass
        elif message.transaction_policy == TransactionPolicy.EXPLICIT:
            # Mark for explicit commit (implement if needed)
            pass
        
        # Send result
        result_msg = ResultMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            execution_id=message.id,
            value=getattr(executor, '_result', None),
        )
        await self._transport.send_message(result_msg)
        
    except Exception as e:
        # FAILURE PATH - Apply transaction policy
        if message.transaction_policy == TransactionPolicy.ROLLBACK_ON_FAILURE:
            # Restore snapshot (like exec-py)
            if ns_snapshot is not None:
                self._namespace.clear()
                self._namespace.update(ns_snapshot)
                # Re-setup builtins if needed
                import builtins
                self._namespace["__builtins__"] = builtins
        
        # Send error
        error_msg = ErrorMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            execution_id=message.id,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        await self._transport.send_message(error_msg)
```

**Evidence from exec-py**:
```python
# exec-py/src/pyrepl/runner_async.py:211, 268-270
op.ns_snapshot = {k: v for k, v in self._global_ns.items()}
# ... later on failure ...
if op.tx_policy in ("rollback_on_failure", "explicit"):
    op.ns = {k: v for k, v in op.ns_snapshot.items()}  # restore
```

---

## Feature Implementation 1: Checkpoint/Restore

### Implementation
**Location**: `/src/subprocess/worker.py`, add handlers:

```python
async def handle_checkpoint(self, message: CheckpointMessage) -> None:
    """Create checkpoint with source code preservation (like pyrepl2)."""
    
    # Extract function and class sources
    self._extract_sources()
    
    checkpoint_data = {
        "version": 1,
        "namespace": self._serialize_namespace(),
        "function_sources": self._function_sources,
        "class_sources": self._class_sources,
        "imports": self._imports,
        "execution_count": self._execution_count,
    }
    
    # Multi-tier serialization (from pyrepl2)
    serialized = None
    error_msg = None
    
    try:
        import cloudpickle
        serialized = cloudpickle.dumps(checkpoint_data)
    except Exception as e1:
        try:
            import pickle
            serialized = pickle.dumps(checkpoint_data, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e2:
            try:
                import json
                serialized = json.dumps(checkpoint_data).encode('utf-8')
            except Exception as e3:
                error_msg = f"Failed all serialization: {e1}, {e2}, {e3}"
    
    if serialized:
        checkpoint_id = str(uuid.uuid4())
        # Store checkpoint (in memory or disk)
        self._checkpoints[checkpoint_id] = serialized
        
        # Send response
        response = CheckpointCreatedMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            checkpoint_id=checkpoint_id,
            size_bytes=len(serialized),
        )
        await self._transport.send_message(response)
    else:
        # Send error
        error_msg = ErrorMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            error=error_msg or "Checkpoint failed",
        )
        await self._transport.send_message(error_msg)

def _extract_sources(self) -> None:
    """Extract source code for functions and classes (like pyrepl2)."""
    import inspect
    import types
    
    for name, obj in self._namespace.items():
        if name.startswith("__"):
            continue
            
        try:
            # Extract function source
            if callable(obj) and not isinstance(obj, type):
                if name not in self._function_sources:
                    try:
                        source = inspect.getsource(obj)
                        self._function_sources[name] = source
                    except:
                        pass  # Built-in or C function
            
            # Extract class source
            elif isinstance(obj, type):
                if name not in self._class_sources:
                    try:
                        source = inspect.getsource(obj)
                        self._class_sources[name] = source
                    except:
                        pass  # Built-in class
            
            # Track imports
            elif isinstance(obj, types.ModuleType):
                import_stmt = f"import {obj.__name__}"
                if import_stmt not in self._imports:
                    self._imports.append(import_stmt)
        except:
            continue

def _serialize_namespace(self) -> dict:
    """Serialize namespace safely (from exec-py pattern)."""
    safe_ns = {}
    for name, obj in self._namespace.items():
        if name.startswith("__") and name != "__name__":
            continue
        try:
            # Test serializability
            import pickle
            pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
            safe_ns[name] = obj
        except:
            # Skip non-serializable objects
            pass
    return safe_ns

async def handle_restore(self, message: RestoreMessage) -> None:
    """Restore from checkpoint."""
    checkpoint_data = self._checkpoints.get(message.checkpoint_id)
    
    if not checkpoint_data:
        # Send error
        error_msg = ErrorMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            error=f"Checkpoint {message.checkpoint_id} not found",
        )
        await self._transport.send_message(error_msg)
        return
    
    # Deserialize
    try:
        import cloudpickle
        data = cloudpickle.loads(checkpoint_data)
    except:
        try:
            import pickle
            data = pickle.loads(checkpoint_data)
        except:
            import json
            data = json.loads(checkpoint_data.decode('utf-8'))
    
    # Clear and restore namespace
    self._namespace.clear()
    self._namespace.update(data.get("namespace", {}))
    self._function_sources = data.get("function_sources", {})
    self._class_sources = data.get("class_sources", {})
    self._imports = data.get("imports", [])
    
    # Re-execute function and class sources
    for source in self._function_sources.values():
        exec(source, self._namespace)
    for source in self._class_sources.values():
        exec(source, self._namespace)
    
    # Re-execute imports
    for import_stmt in self._imports:
        exec(import_stmt, self._namespace)
    
    # Send success
    response = RestoredMessage(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        checkpoint_id=message.checkpoint_id,
    )
    await self._transport.send_message(response)
```

---

## Feature Implementation 2: Simplified Output Streaming

### Option A: StringIO Approach (Like pyrepl2)
```python
def execute_code(self, code: str) -> None:
    """Execute with simple output capture."""
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    
    try:
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            exec(compile(code, "<session>", "exec"), self._namespace)
        
        # Send complete output after execution
        if stdout_data := stdout_buffer.getvalue():
            asyncio.run_coroutine_threadsafe(
                self._send_output(stdout_data, StreamType.STDOUT),
                self._loop
            )
        if stderr_data := stderr_buffer.getvalue():
            asyncio.run_coroutine_threadsafe(
                self._send_output(stderr_data, StreamType.STDERR),
                self._loop
            )
    except Exception as e:
        self._error = e
        # Capture traceback
        with redirect_stderr(stderr_buffer):
            traceback.print_exc()
        if stderr_data := stderr_buffer.getvalue():
            asyncio.run_coroutine_threadsafe(
                self._send_output(stderr_data, StreamType.STDERR),
                self._loop
            )
```

### Option B: Direct Streaming (Simpler Current Approach)
```python
# Simplify OutputCapture to remove periodic flushing
class SimpleOutputCapture:
    def __init__(self, transport, stream_type, execution_id):
        self._transport = transport
        self._stream_type = stream_type
        self._execution_id = execution_id
        
    def write(self, data: str) -> int:
        """Send output immediately."""
        if data:
            message = OutputMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                data=data,
                stream=self._stream_type,
                execution_id=self._execution_id,
            )
            # Send directly
            asyncio.run_coroutine_threadsafe(
                self._transport.send_message(message),
                asyncio.get_event_loop()
            )
        return len(data)
    
    def flush(self) -> None:
        """No buffering, nothing to flush."""
        pass
```

---

## Testing Strategy

### Test 1: Verify Input Persistence
```python
async def test_input_persistence_fixed():
    """Test that input override persists across executions."""
    session = Session()
    await session.start()
    
    try:
        # First execution with input
        code1 = "name = input('Enter name: ')"
        task1 = asyncio.create_task(session.execute(code1))
        
        # Wait for input request
        async for msg in task1:
            if isinstance(msg, InputMessage):
                await session.input_response(msg.id, "Alice")
                break
        
        # Complete first execution
        await task1
        
        # Second execution - input should still work
        code2 = "age = input('Enter age: ')"
        task2 = asyncio.create_task(session.execute(code2))
        
        async for msg in task2:
            if isinstance(msg, InputMessage):
                await session.input_response(msg.id, "30")
                break
        
        await task2
        
        # Verify both variables exist
        result = await session.execute("f'{name} is {age} years old'")
        assert result.value == "Alice is 30 years old"
        
    finally:
        await session.shutdown()
```

### Test 2: Verify Transaction Rollback
```python
async def test_transaction_rollback():
    """Test that rollback restores namespace."""
    session = Session()
    await session.start()
    
    try:
        # Set initial state
        await session.execute("x = 10")
        
        # Execute with rollback on failure
        msg = ExecuteMessage(
            id="test-tx",
            timestamp=time.time(),
            code="x = 20; y = 30; raise ValueError('Test error')",
            transaction_policy=TransactionPolicy.ROLLBACK_ON_FAILURE,
        )
        
        # Should fail and rollback
        try:
            await session.execute(msg)
        except Exception:
            pass  # Expected
        
        # Check namespace was rolled back
        result = await session.execute("x")
        assert result.value == 10  # Original value
        
        result = await session.execute("'y' in dir()")
        assert result.value is False  # y should not exist
        
    finally:
        await session.shutdown()
```

---

## Implementation Timeline

### Day 1: Critical Bug Fixes
1. Fix input override persistence (executor.py:199)
2. Update test pattern to reuse sessions
3. Run full test suite to verify fixes

### Day 2: Transaction Support
1. Implement namespace snapshots
2. Add transaction handling in worker.py
3. Test all transaction policies

### Day 3: Checkpoint/Restore
1. Implement source extraction
2. Add checkpoint/restore handlers
3. Test with functions, classes, and imports

### Day 4: Output Streaming
1. Choose between StringIO or simplified direct approach
2. Implement and benchmark
3. Test with large outputs

### Day 5: Integration Testing
1. Full end-to-end tests
2. Performance benchmarking
3. Documentation updates

---

## Success Metrics

| Feature | Before Fix | After Fix | Test |
|---------|------------|-----------|------|
| Input persistence | ❌ Resets each execution | ✅ Persists | `test_input_persistence_fixed` |
| Namespace persistence | ❌ New subprocess each test | ✅ Reuses session | `test_namespace_persistence` |
| Transactions | ❌ Not implemented | ✅ Rollback works | `test_transaction_rollback` |
| Checkpoints | ❌ Not implemented | ✅ Save/restore | `test_checkpoint_restore` |
| Output > 1MB | ⚠️ Returns 0 bytes | ✅ Streams correctly | `test_large_output` |

---

## Key Insights

1. **PyREPL3 is 90% there** - The architecture is solid, just needs these targeted fixes
2. **Input bug is one line** - Remove `builtins.input = original_input`
3. **Session reuse is critical** - This is why pyrepl2 works
4. **Transactions are simple** - Just dict snapshots like exec-py
5. **Output can be simplified** - Current approach is over-engineered

With these fixes, PyREPL3 will combine:
- pyrepl2's persistent session model
- exec-py's elegant transaction handling
- Its own superior message protocol

The result will be a production-ready execution service that surpasses both predecessors.