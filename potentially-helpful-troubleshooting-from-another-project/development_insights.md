# Development Insights from v0.1 Investigation

## Executive Summary
This document captures critical insights from debugging v0.1 protocol incompatibilities, providing actionable guidance for future development and debugging efforts on the exec-py codebase.

## Critical Anti-Patterns to Avoid

### 1. Protocol Inconsistency
**Anti-pattern**: Different components using different serialization protocols in the same system
```python
# BAD: runner_async.py
msg = unpack(data)  # Expects raw bytes, dictionary format

# BAD: manager.py  
frame = await read_frame(reader)  # Returns Frame object
```

**Solution**: Establish protocol contracts early and enforce them
```python
# GOOD: Consistent protocol across all components
frame = await read_frame(reader)  # All components use Frame
await write_frame(writer, frame)   # Symmetric operations
```

### 2. Blocking Async Event Handlers
**Anti-pattern**: Event handler waiting for events it should receive
```python
# BAD: Deadlock waiting for input in same handler
async def handle(self, frame):
    if frame.kind == "exec_stream":
        fut = asyncio.Future()
        self.op_wait[op_id] = fut
        await self.send_event("INPUT_REQUEST", {...})
        await fut  # DEADLOCK: Can't receive input_response
```

**Solution**: Use async tasks for operations that wait for responses
```python
# GOOD: Non-blocking handler
async def handle(self, frame):
    if frame.kind == "exec_stream":
        asyncio.create_task(self._handle_exec_with_input(op_id))
        # Returns immediately, can handle more frames
```

### 3. Complex Connection Setup
**Anti-pattern**: Using TCP servers when simpler alternatives exist
```python
# BAD: Complex TCP server setup
server = await asyncio.start_server(handler, "127.0.0.1", 0)
await server.wait_closed()  # Can hang
```

**Solution**: Use socketpair for testing bidirectional communication
```python
# GOOD: Simple, reliable socketpair
sock1, sock2 = socket.socketpair()
# Direct bidirectional communication, no server management
```

## Effective Debugging Strategies

### 1. Protocol Boundary Inspection
**First Step**: Always compare imports and protocol usage across components
```bash
# Quick protocol consistency check
grep -h "from.*protocol import" v0_1/*.py | sort | uniq

# Find protocol function usage
grep -n "write_frame\|read_frame\|pack\|unpack" v0_1/*.py
```

### 2. Progressive Test Complexity
Start with the simplest possible test case:
```python
# Level 1: Basic connection
async def test_connection():
    client = RunnerClient(reader, writer)
    await client.start()
    await client.stop()

# Level 2: Simple execution (no input)
async def test_simple_exec():
    result = await client.exec("print('hello')")
    
# Level 3: Complex execution (with input)
async def test_with_input():
    result = await client.exec("x = input(); print(x)")
```

### 3. Strategic Debug Output
Add debug output at critical points:
```python
# Protocol boundaries
print(f"Sending frame: {frame}")
print(f"Received frame: {frame}")

# State transitions  
print(f"State change: {old_state} -> {new_state}")

# Async operations
print(f"Starting async operation: {op_id}")
print(f"Async operation completed: {op_id}")
```

## Architecture Patterns for Reliability

### 1. Clear Protocol Layers
```
Application Layer (Manager/Runner logic)
           ↓
Protocol Layer (Frame serialization)
           ↓  
Transport Layer (asyncio streams)
```

Each layer should have clear interfaces and not leak abstractions.

### 2. Operation Tracking Pattern
Every async operation needs:
- Unique identifier (op_id)
- State tracking (pending/active/completed)
- Timeout handling
- Cancellation support

```python
class Operation:
    def __init__(self, op_id: str):
        self.op_id = op_id
        self.state = "pending"
        self.result_future = asyncio.Future()
        self.timeout_task = None
```

### 3. Event-Driven Architecture
Components should emit events, not call each other directly:
```python
# GOOD: Event-driven
await self.send_event("OP_STARTED", {"op_id": op_id})
await self.send_event("OUTPUT", {"data": output})
await self.send_event("OP_COMPLETED", {"result": result})

# BAD: Direct coupling
await other_component.handle_output(output)
```

## Investigation Process Improvements

### 1. Systematic Comparison First
Before debugging symptoms:
1. Compare component interfaces
2. Verify protocol consistency
3. Check data flow assumptions
4. Validate serialization formats

### 2. Hypothesis-Driven Debugging
Structure investigations as:
```
Observation → Hypothesis → Test → Falsification/Validation → Next Hypothesis
```

Document each step to avoid repeating failed approaches.

### 3. Minimal Reproducible Cases
Before debugging complex scenarios:
1. Create minimal test that shows the issue
2. Remove all unnecessary complexity
3. Isolate the specific failing operation
4. Add complexity back incrementally

## Common Failure Modes in Async Systems

### 1. Silent Hangs
**Symptoms**: No errors, process appears stuck
**Common Causes**:
- Deadlocks in async operations
- Protocol mismatches causing infinite waits
- Missing timeout handling

**Diagnostic Approach**:
```python
# Add timeouts to all async operations
async with asyncio.timeout(10):
    result = await operation()
    
# Add progress indicators
print(f"Step 1: {timestamp()}")
await step1()
print(f"Step 2: {timestamp()}")
```

### 2. Race Conditions
**Symptoms**: Intermittent failures, order-dependent bugs
**Common Causes**:
- Multiple writers to shared state
- Uncoordinated async tasks
- Missing synchronization

**Solution Pattern**:
```python
# Use locks for shared state
async with self._lock:
    self._state = new_state
    
# Use queues for coordination
await self._event_queue.put(event)
```

### 3. Resource Leaks
**Symptoms**: Memory growth, file descriptor exhaustion
**Common Causes**:
- Unclosed connections
- Unfinished async tasks
- Missing cleanup handlers

**Prevention**:
```python
# Always use context managers
async with RunnerClient() as client:
    result = await client.exec(code)
    
# Always cancel tasks on cleanup
def cleanup(self):
    for task in self._tasks:
        task.cancel()
```

## Testing Best Practices

### 1. Test Isolation
Each test should:
- Create its own resources
- Clean up completely
- Not depend on test order
- Not share state with other tests

### 2. Timeout Everything
```python
@pytest.mark.asyncio
@pytest.mark.timeout(10)  # pytest-timeout
async def test_something():
    async with asyncio.timeout(5):  # operation timeout
        result = await operation()
```

### 3. Test Both Success and Failure Paths
```python
async def test_operation_success():
    result = await operation()
    assert result.success
    
async def test_operation_timeout():
    with pytest.raises(asyncio.TimeoutError):
        await operation(timeout=0.001)
        
async def test_operation_cancellation():
    task = asyncio.create_task(operation())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
```

## Performance Considerations

### 1. Avoid Synchronous Operations in Async Code
```python
# BAD: Blocks event loop
def process_data(data):
    time.sleep(1)  # Blocks everything
    return data

# GOOD: Use async equivalents
async def process_data(data):
    await asyncio.sleep(1)  # Yields to event loop
    return data
```

### 2. Batch Operations When Possible
```python
# BAD: Many small operations
for item in items:
    await process(item)
    
# GOOD: Batch processing
await asyncio.gather(*[process(item) for item in items])
```

### 3. Use Appropriate Queue Sizes
```python
# Consider memory vs responsiveness tradeoffs
self._event_queue = asyncio.Queue(maxsize=100)  # Bounded
self._result_cache = {}  # Unbounded - needs management
```

## Documentation Standards

### 1. Protocol Documentation
Every protocol should document:
- Message format (schema)
- Valid state transitions
- Error conditions
- Example message sequences

### 2. Async Boundary Documentation
```python
async def operation():
    """
    Performs operation X.
    
    Async behavior:
    - May block for up to 30 seconds waiting for response
    - Raises TimeoutError if no response received
    - Can be safely cancelled at any time
    """
```

### 3. Debug Information
Include in error messages:
- Current state
- Expected vs actual values
- Suggestions for resolution

```python
raise ValueError(
    f"Protocol mismatch: expected Frame, got {type(msg).__name__}. "
    f"Ensure all components use v0.1 protocol."
)
```

## Quick Reference Checklist

### Before Starting Development
- [ ] Review existing protocol specifications
- [ ] Check component interface compatibility  
- [ ] Plan async operation flow
- [ ] Design error handling strategy

### During Development
- [ ] Add debug logging at protocol boundaries
- [ ] Test with minimal cases first
- [ ] Handle timeouts and cancellations
- [ ] Document async behavior

### When Debugging
- [ ] Check protocol consistency first
- [ ] Look for blocking async operations
- [ ] Add timeout to identify hangs
- [ ] Create minimal reproducible case
- [ ] Document hypotheses and tests

### Before Deployment
- [ ] All async operations have timeouts
- [ ] Resources are properly cleaned up
- [ ] Error messages are informative
- [ ] Tests cover success and failure paths

## Conclusion

The v0.1 investigation revealed that seemingly simple issues (tests hanging) can stem from multiple compounding problems (protocol mismatch + async deadlock). Success in debugging such issues requires:

1. **Systematic investigation** - Don't skip the basics
2. **Clear hypotheses** - Test one thing at a time
3. **Progressive complexity** - Start simple, add complexity
4. **Documentation** - Track what you've tried
5. **Protocol discipline** - Consistency is critical

The combination of proper async patterns, consistent protocols, and systematic debugging approaches will prevent and quickly resolve similar issues in the future.