# Event vs Condition: The Single-Consumer Trap

## The Problem

`asyncio.Event` with clear-after-wait pattern is fundamentally incompatible with multiple sequential reads because:

- **Event.clear() is GLOBAL state modification**
- **The decision to clear is LOCAL to one consumer**
- **In multi-consumer scenarios, this creates an ownership conflict**

## The Anti-Pattern

```python
# ❌ DON'T DO THIS
async def readexactly(n):
    while len(buffer) < n:
        await self.event.wait()
        self.event.clear()  # ← WHO OWNS THIS CLEAR?
```

### Why It Fails

1. Event is **binary** (set/clear) but buffer state is **continuous** (0 to N bytes)
2. Multiple consumers (e.g., header reader, body reader) share one event
3. First consumer clears, leaving subsequent consumers unable to detect new data
4. `set()` on already-set Event does nothing - signals can be lost

## The Correct Pattern

```python
# ✅ DO THIS INSTEAD
async def readexactly(n):
    async with self.condition:
        await self.condition.wait_for(
            lambda: len(self.buffer) >= self.read_pos + n
        )
```

### Why It Works

- **No explicit clear()** - state is the buffer content itself
- **Each waiter has its own predicate** - checks its specific need
- **notify_all() wakes ALL waiters** - each re-evaluates independently
- **State-based, not event-based** - "buffer has N bytes" not "bytes arrived"

## Demonstrations

### See the Bug in Action

```bash
python deep_dive.py
```

This demonstrates:
- How Event fails with multiple sequential reads
- Why Condition succeeds in the same scenario
- The exact race condition that causes deadlocks

### Reproduce the Exact Bug

```bash
python exact_bug_reproduction.py
```

This shows:
- The exact MockStreamPair bug scenario
- How batch writes trigger the deadlock
- Why the timing matters

## Key Insights

### Event Semantics
- `Event.set()` wakes ALL current waiters
- `Event.clear()` affects global state
- Once cleared, new waiters must wait for next `set()`
- Problem: Who should clear? When?

### Condition Semantics
- `wait_for(predicate)` checks condition
- No explicit `clear()` needed
- `notify_all()` wakes all waiters to re-check
- Each waiter independently evaluates if ready

## Decision Matrix

| Scenario | Use Event | Use Condition | Why |
|----------|-----------|---------------|-----|
| Shutdown signal | ✅ | ❌ | One-time broadcast, no reset |
| Buffer has data | ❌ | ✅ | State-based, multiple consumers |
| Task complete | ✅ | ❌ | Single occurrence |
| Queue not empty | ❌ | ✅ | State that changes over time |
| Connection ready | ✅ | ❌ | One-time transition |

## The Three Corollaries

1. **If you find yourself clearing an Event, ask "who owns this clear?"**
2. **If multiple entities wait on one Event, you probably want Condition**
3. **Test the batch case - it reveals races that sequential operations hide**

## Common Mistakes

### Mistake 1: Clear in Consumer
```python
# ❌ WRONG
await event.wait()
event.clear()  # Consumer shouldn't own this
```

### Mistake 2: Multiple set() Calls
```python
# ❌ INEFFECTIVE
event.set()  # First time: works
event.set()  # Already set: does nothing
```

### Mistake 3: Event for Buffer State
```python
# ❌ WRONG PRIMITIVE
self.data_available = asyncio.Event()  # Binary
# But buffer can have 0, 10, 100... bytes (continuous)
```

## Testing Strategy

Always test these scenarios:
1. **Batch writes** - All data written before any reads
2. **Sequential reads** - Multiple reads from same consumer
3. **Concurrent readers** - Multiple consumers reading simultaneously
4. **Zero delays** - No sleep() calls to hide races

## Summary

**Use Event when:** Broadcasting a one-time occurrence to multiple waiters

**Use Condition when:** Multiple consumers need to check if state meets their specific requirements

**For protocol framing:** ALWAYS use Condition or real streams - never Event with clear

---

*Remember: If you're doing `await event.wait(); event.clear()`, you're probably in single-consumer territory. If you have multiple consumers (including sequential reads from same consumer), you need a different pattern.*