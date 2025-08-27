# AsyncIO Patterns: Event vs Condition and Protocol Framing

This documentation captures critical learnings from debugging asyncio synchronization issues in the exec-py project, specifically the MockStreamPair deadlock that affected test_working_manager.py.

## 🎯 The Core Insight

> **"Event represents occurrence, Condition represents state. Protocol framing is about state (buffer has N bytes), not occurrence (bytes arrived)."**

## 📚 Documentation Structure

### [Event vs Condition](./event-vs-condition/)
Deep analysis of when to use `asyncio.Event` vs `asyncio.Condition`, including the exact bug that caused test deadlocks.

### [Protocol Framing](./protocol-framing/)
Understanding two-phase reads in length-prefixed protocols and why they require special synchronization patterns.

### [Principles](./principles/)
General principles and a comprehensive model of deadlock scenarios in async stream protocols.

### [Debugging](./debugging/)
Tools and techniques for debugging async synchronization issues.

## 🚨 The Problem We Solved

The MockStreamPair class used `asyncio.Event` with a clear-after-wait pattern:

```python
# THE BUG
async def readexactly(n):
    while buffer_not_enough():
        await self.event.wait()
        self.event.clear()  # ← Problem: Who owns this clear?
```

This caused deadlocks when:
1. Multiple frames were written in batch
2. Reader performed sequential reads (header then body)
3. Event was cleared by first read, blocking subsequent reads

## ✅ The Solution

Replace Event with Condition:

```python
# THE FIX
async def readexactly(n):
    async with self.condition:
        await self.condition.wait_for(
            lambda: len(self.buffer) >= self.read_pos + n
        )
```

## 🔍 Quick Decision Guide

```
Need async synchronization?
├─ One-shot broadcast? → Event (no clear)
├─ Single consumer? → Queue
├─ Multiple consumers checking state? → Condition
└─ Protocol with framing? → ALWAYS Condition or real streams
```

## 📊 Test Results

After applying these patterns:
- ✅ All 32 tests passing
- ✅ No more deadlocks
- ✅ Consistent behavior with batch and sequential operations

## 🧪 Interactive Demonstrations

Run the demonstrations to see the patterns in action:

```bash
# See Event vs Condition comparison
python docs/asyncio-patterns/event-vs-condition/deep_dive.py

# Understand protocol framing
python docs/asyncio-patterns/protocol-framing/framing_analysis.py

# Explore deadlock scenarios
python docs/asyncio-patterns/principles/deadlock_model.py
```

## 📝 Key Takeaways

1. **Event.clear() ownership is ambiguous** in multi-consumer scenarios
2. **Protocol framing creates multiple consumers** (header reader, body reader)
3. **Test with batch operations** to expose synchronization bugs
4. **State-based synchronization (Condition) > Event-based** for buffers
5. **Real streams (socketpair) > Mocks** when possible

## 🔗 Related Files

- Fixed test: `tests/integration/test_working_manager.py`
- Investigation log: `troubleshooting/v0_1_investigation_log.json`
- Original issue: MockStreamPair class deadlock

---

*This documentation was created after extensive debugging of asyncio synchronization issues. The patterns and principles here are battle-tested and proven to work in production async code.*