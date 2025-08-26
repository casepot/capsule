# General Principles: Deadlock Models and Patterns

## Core Insights

1. **Events are single-notification, Conditions are state-based**
2. **Clear ownership must be unambiguous**
3. **Protocol framing requires multi-consumer patterns**
4. **State-based > event-based for complex scenarios**
5. **Test with batch operations, not just sequential**

## Comprehensive Deadlock Model

Run the interactive model:
```bash
python deadlock_model.py
```

### Five Types of Deadlocks

#### 1. Consumer Race Deadlock
- **Type:** Multiple consumers, single notification
- **Cause:** Event cleared by first consumer blocks others
- **Symptoms:** Works with delays, fails without
- **Prevention:** Use Condition with predicates

#### 2. Clear Ownership Deadlock
- **Type:** Unclear who should clear event
- **Cause:** No defined ownership of clear() operation
- **Symptoms:** Intermittent failures, timing-dependent
- **Prevention:** Avoid Event.clear() in consumers

#### 3. Timing-Dependent Race
- **Type:** Race between wait() and set()
- **Cause:** set() called before wait() starts
- **Symptoms:** Works in debug, fails in production
- **Prevention:** State-based waiting with Condition

#### 4. Resource Starvation
- **Type:** Consumer waiting for consumed resource
- **Cause:** First consumer takes notification, others starve
- **Symptoms:** Random consumer starvation
- **Prevention:** Queue per consumer or Condition

#### 5. Circular Wait
- **Type:** A waits for B, B waits for A
- **Cause:** Synchronous wait in async context
- **Symptoms:** Complete freeze, no CPU usage
- **Prevention:** Always use async patterns

## Decision Tree

```
Need to notify waiters?
├─ One-shot broadcast to all?
│  └─ Use Event (don't clear in consumers)
├─ Single consumer per item?
│  └─ Use Queue or Channel
├─ Multiple consumers checking state?
│  └─ Use Condition with predicates
└─ Protocol with framing?
   └─ ALWAYS use Condition or real streams
```

## Anti-Patterns to Avoid

### ❌ Clear-After-Wait
```python
await event.wait()
event.clear()  # Assumes single consumer
```
**Fix:** Use Condition or Queue

### ❌ Set-Without-Check
```python
event.set()  # Multiple times - later sets do nothing
```
**Fix:** Use notify_all() with Condition

### ❌ Global Event for Local State
```python
self.event  # For buffer reads - Event is binary, buffer isn't
```
**Fix:** Condition checking buffer size

## Correct Patterns

### ✅ Predicate-Based Waiting
```python
async with cond:
    await cond.wait_for(lambda: state_ok())
```
**Why:** Each waiter checks its specific need

### ✅ Broadcast with Condition
```python
async with cond:
    cond.notify_all()
```
**Why:** All waiters re-evaluate their predicates

### ✅ Queue for Distribution
```python
await queue.get()
```
**Why:** Each item consumed exactly once

### ✅ Real Streams for I/O
```python
sock1, sock2 = socket.socketpair()
```
**Why:** OS handles all synchronization

## Testing Guidelines

### Must Test Scenarios

1. **Batch Operations**
   - Write all data at once
   - Then read sequentially
   - Exposes clear/wait races

2. **Multiple Concurrent Readers**
   - Start multiple read tasks
   - Write data
   - Check all readers progress

3. **Reader Catching Up**
   - Writer writes 10 items
   - Reader reads 15 items
   - Must handle "no more data" correctly

4. **Zero Delays**
   - No asyncio.sleep() calls
   - Exposes true race conditions
   - Tests worst-case scheduling

5. **Cancellation Paths**
   - Cancel during wait
   - Cancel during read
   - Ensure clean shutdown

### Test Template

```python
async def test_pattern():
    # Setup
    buffer = YourBuffer()
    
    # Batch write (worst case)
    for data in all_data:
        buffer.write(data)
    
    # Sequential reads
    results = []
    for _ in range(len(all_data)):
        results.append(await buffer.read())
    
    # Verify
    assert results == all_data
    
    # Test exhaustion
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(buffer.read(), timeout=0.1)
```

## Debugging Techniques

### 1. Event State Logging
```python
print(f"Event state: {'SET' if event.is_set() else 'CLEAR'}")
# Log at every wait/set/clear
```

### 2. Buffer Visualization
```python
print(f"Buffer: {len(buffer)} bytes, read_pos: {read_pos}")
# Track buffer state changes
```

### 3. Timeout Everything
```python
result = await asyncio.wait_for(operation(), timeout=1.0)
# Never wait forever during debug
```

### 4. Timeline Analysis
```python
T1: Writer.write(data1)
T2: Event.set()
T3: Reader1.wait() returns
T4: Reader1.clear()
T5: Writer.write(data2)
T6: Event.set() - but already set!
T7: Reader2.wait() - waits forever
```

### 5. Thread Monitoring
```python
import threading
print(f"Threads: {threading.active_count()}")
# Should be stable in pure async
```

## The Fundamental Theorem

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  "Event represents occurrence, Condition represents    │
│   state. Protocol framing is about state (buffer      │
│   has N bytes), not occurrence (bytes arrived)."       │
│                                                         │
│  Therefore: Use Condition for protocol framing.        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Corollaries

1. **If you find yourself clearing an Event, ask "who owns this clear?"**
2. **If multiple entities wait on one Event, you probably want Condition**
3. **Test the batch case - it reveals races that sequential operations hide**

## Common Scenarios and Solutions

| Scenario | Wrong Approach | Right Approach |
|----------|---------------|----------------|
| Buffer has N bytes | Event + clear | Condition with predicate |
| Task pool complete | Individual Events | Single Condition or gather() |
| Message queue | Event for "has items" | Queue.get() with wait |
| Rate limiting | Event timer | Semaphore or token bucket |
| Reader/Writer lock | Multiple Events | asyncio.Lock + Condition |

## Summary

The key to avoiding deadlocks in async code:

1. **Match primitive to requirement** - Event for occurrences, Condition for state
2. **Test worst cases** - Batch operations, zero delays, concurrent access
3. **Avoid ownership ambiguity** - Clear responsibilities for state changes
4. **Prefer higher-level abstractions** - Queue > Condition > Event
5. **Use real I/O when possible** - socketpair > mock streams

---

*These principles were derived from real debugging sessions and represent battle-tested patterns for async synchronization.*