# Implementation Archaeology

## The Three Critical Issues

PyREPL3 started with three blocking problems. Understanding their solutions reveals design constraints:

### 1. Input Handling (SOLVED)

**Problem**: EOFError on any input() call
**Root Cause**: stdin owned by protocol, not available for user code
**Solution**: Thread-based execution with protocol input

Investigate:
- `src/subprocess/executor.py:84-118` - Protocol input implementation
- Why threads instead of async input?
- What broke with the async approach?

### 2. Pool Deadlocks (UNSOLVED)

**Problem**: Third concurrent acquisition hangs
**Suspected Cause**: Lock held while creating sessions

Look for patterns:
- `src/session/pool.py` - ensure_min_sessions method
- Where are locks acquired and released?
- What operations happen under lock?

### 3. API Layer (NOT STARTED)

**Problem**: No network access
**Planned Solution**: WebSocket + REST

Consider:
- Where would API server live?
- How would it route to sessions?
- Authentication/authorization needs?

## Lessons from Predecessors

### From exec-py

- FD separation for protocol
- Thread-based execution works for blocking I/O
- Single unified architecture

Questions:
- Why didn't PyREPL3 adopt FD separation?
- What patterns were consciously avoided?

### From pyrepl2

- Session pool complexity
- Health monitoring needs
- Warmup benefits

Investigate:
- Which pyrepl2 patterns were adopted?
- What deadlock patterns were avoided?
- Why different pool implementation?

## Architectural Decisions

### Why Subprocesses?

Trace the decision:
- Isolation requirements
- Resource limit enforcement  
- Crash recovery

But consider:
- When is process overhead worth it?
- Could threads + sandboxing work?
- What about WASM isolation?

### Why Binary Protocol?

MessagePack chosen over:
- JSON (why not simpler?)
- Protobuf (why not typed?)
- Custom (why not minimal?)

Look at:
- `src/protocol/transport.py` - Serialization logic
- Message size patterns
- Performance implications

### Why Thread + Async Hybrid?

Current: Async infrastructure, threaded execution
- What drove this split?
- Could it be unified?
- Performance implications?

## Failed Approaches to Study

### Dual-Reader Architecture (v0)
- Multiple stdin readers
- Race conditions
- Why did it seem reasonable initially?

### Single-Thread Async (attempted?)
- Pure async execution
- What broke?
- Why threads necessary?

## Design Constraints Discovered

List of "invariants" that might not be:

1. "Only one stdin reader" - Could FD separation relax this?
2. "Protocol owns stdio" - Could we multiplex?
3. "One process per session" - Could we share processes?
4. "Threads for user code" - Could async work with changes?

## Questions for Future Investigation

1. What assumptions from Python could be relaxed for other languages?
2. Which constraints are fundamental vs incidental?
3. What would a v2 designed from scratch look like?
4. Are we solving the right problem?