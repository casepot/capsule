# PyREPL3 Remaining Issues Fix Planning Prompt

## Your Mission
You are tasked with planning fixes for two critical issues in PyREPL3 that prevent session warmup and pool creation from working, while preserving all existing functionality and the single-reader architecture that prevents deadlocks.

## Context

### Historical Context (Problem Archaeology)

#### Previous Failures and Lessons
1. **v0.1 Dual-Reader Architecture**: Initially had main thread + control thread both reading stdin
   - **Failure**: Race conditions and deadlocks after streaming operations
   - **Lesson**: File descriptors are single-consumer resources
   - **Invariant Discovered**: Single-reader architecture prevents races

2. **Missing transport.start() in worker**: Worker created MessageTransport but never started the background reader
   - **Failure**: Execute messages never received by worker
   - **Fix Applied**: Added `await transport.start()` in worker main() line 524
   - **Lesson**: Background asyncio tasks must be explicitly started

3. **FrameReader timeout race conditions**: 0.1s timeout was too aggressive
   - **Failure**: Messages dropped during normal operation
   - **Fix Applied**: Increased timeout to 1.0s
   - **Lesson**: Length-prefixed protocols need generous timeouts for two-phase reads

### Existing Infrastructure (Architecture Recognition)

#### Working Components
- **MessageTransport**: Binary framed protocol with msgpack serialization (fully working)
- **FrameReader**: Background _read_loop with asyncio.Condition for synchronization (working)
- **Session.execute()**: Successfully sends ExecuteMessage and receives responses via message queues
- **Message Routing**: Routes by execution_id to correct queue handlers
- **Worker Execute Handler**: Processes ExecuteMessage and sends OutputMessage/ResultMessage/ErrorMessage

#### Critical Architecture Elements
1. **Session._receive_loop** (lines 162-196): Background task receiving messages from subprocess
2. **Session.execute()** (lines 217-290): Creates per-execution message queue, waits for responses
3. **Session._route_message()** (lines 198-215): Routes messages to execution-specific queues
4. **Session States**: CREATING → WARMING → READY → IDLE/BUSY → SHUTTING_DOWN → TERMINATED

#### Communication Flow
```
Session.execute() → PipeTransport → MessageTransport → FrameWriter → subprocess.stdin
                                                                            ↓
Worker.execute() ← MessageTransport ← FrameReader._read_loop ← subprocess.stdout
       ↓
   ResultMessage → MessageTransport → FrameWriter → subprocess.stdout
                                                            ↓
Session._receive_loop ← MessageTransport ← FrameReader ← subprocess.stdin
```

## Current Problems

### Problem 1: Session Warmup Deadlock
**Location**: src/session/manager.py lines 144-160
**Symptom**: Sessions with warmup_code hang indefinitely during start()
**Evidence**: 
```python
# This works:
session = Session()
await session.start()  # ✅ Completes in <1s

# This hangs:
session = Session(warmup_code="x = 1")
await session.start()  # ❌ Timeout after 10s
```

**Current Flow**:
1. Session.start() creates subprocess and transport
2. Starts _receive_loop background task
3. Waits for READY message with 10s timeout
4. Ready message IS received (sets _ready_event)
5. Calls _warmup() which calls execute()
6. execute() creates message queue and waits for responses
7. **DEADLOCK**: No responses ever arrive

### Problem 2: SessionPool Parameter Mismatch
**Location**: src/session/pool.py line 31
**Symptom**: Cannot create pool with expected parameters
**Evidence**:
```python
# Expected (doesn't work):
pool = SessionPool(min_size=2, max_size=10)  # ❌ TypeError

# Current requirement:
config = PoolConfig()
config.min_idle = 2
config.max_sessions = 10
pool = SessionPool(config)  # Works but unintuitive
```

## Constraints

### Non-Negotiable Requirements
1. **Single-Reader Invariant**: Only _receive_loop reads from transport (prevents race conditions)
2. **Message Queue Isolation**: Each execution has its own queue (prevents message mixing)
3. **State Machine Integrity**: States must transition in correct order
4. **No Breaking Changes**: All 29 existing tests must continue passing
5. **Background Task Management**: _receive_loop must run continuously during session lifetime

### Risks to Avoid

#### Risk 1: Reintroducing Race Conditions
- **Scenario**: Adding another reader or modifying _receive_loop incorrectly
- **Mitigation**: Maintain single background _receive_loop, never create additional readers

#### Risk 2: Message Queue Deadlock
- **Scenario**: execute() waiting on queue that never receives messages
- **Mitigation**: Ensure _receive_loop is running BEFORE execute() creates queues

#### Risk 3: State Corruption
- **Scenario**: State changes out of order causing invalid operations
- **Mitigation**: Use locks around state transitions, validate state before operations

## Planning Approach

### Solution Space Analysis

#### For Problem 1 (Warmup Deadlock):

**Approach A: State Ordering Fix**
- **Philosophy**: Ensure READY state before warmup execution
- **Key Insight**: execute() requires state in [READY, IDLE, WARMING] but _warmup() runs while still WARMING
- **Implementation**: Set state to READY before warmup, not after
- **Risk**: Might allow external execute() during warmup

**Approach B: Direct Message Send**
- **Philosophy**: Bypass execute() for warmup, send ExecuteMessage directly
- **Key Insight**: Warmup doesn't need the full execute() queue machinery
- **Implementation**: Send ExecuteMessage directly via transport in _warmup()
- **Risk**: Duplicates some execute() logic

**Approach C: Defer Warmup**
- **Philosophy**: Complete start() first, run warmup as first execute()
- **Key Insight**: Separation of initialization from warmup
- **Implementation**: Store warmup_code, execute after reaching READY
- **Risk**: Changes warmup timing semantics

#### For Problem 2 (Pool Parameters):

**Approach A: Kwargs to Config Adapter**
- **Philosophy**: Accept both kwargs and PoolConfig
- **Implementation**: Detect kwargs, build PoolConfig internally
- **Backward Compatible**: Yes
- **Example**: `__init__(self, config=None, **kwargs)`

**Approach B: Factory Method**
- **Philosophy**: Add SessionPool.create() with kwargs
- **Implementation**: Static method that builds config
- **Backward Compatible**: Yes
- **Example**: `SessionPool.create(min_size=2, max_size=10)`

### Recommended Approach Selection

1. **Warmup Fix**: Use **Approach A (State Ordering)** 
   - Minimal change (1-2 lines)
   - Preserves existing execute() flow
   - Aligns with state machine design

2. **Pool Fix**: Use **Approach A (Kwargs Adapter)**
   - Most intuitive API
   - Maintains backward compatibility
   - Standard Python pattern

## Implementation Scaffolding

### Fix 1: Warmup Deadlock Resolution

```python
# In src/session/manager.py, lines 133-136
# CURRENT CODE:
if self._warmup_code:
    await self._warmup()

self._state = SessionState.READY

# FIXED CODE:
# Set READY state BEFORE warmup so execute() can proceed
self._state = SessionState.READY

if self._warmup_code:
    await self._warmup()
    # After warmup, we're back to IDLE (execute() sets it)
```

**Why This Works**:
- execute() checks: `if self._state not in [SessionState.READY, SessionState.IDLE, SessionState.WARMING]`
- Currently _warmup() runs while state is WARMING
- Setting READY first allows execute() to proceed normally
- execute() will set state to BUSY during execution, then IDLE after

### Fix 2: SessionPool Parameter Support

```python
# In src/session/pool.py, lines 31-32
# CURRENT CODE:
def __init__(self, config: Optional[PoolConfig] = None) -> None:
    self._config = config or PoolConfig()

# FIXED CODE:
def __init__(
    self, 
    config: Optional[PoolConfig] = None,
    *,  # Force keyword-only arguments
    min_idle: Optional[int] = None,
    max_sessions: Optional[int] = None,
    session_timeout: Optional[float] = None,
    warmup_code: Optional[str] = None,
    **kwargs
) -> None:
    if config:
        self._config = config
    else:
        # Build config from kwargs
        self._config = PoolConfig()
        if min_idle is not None:
            self._config.min_idle = min_idle
        if max_sessions is not None:
            self._config.max_sessions = max_sessions
        if session_timeout is not None:
            self._config.session_timeout = session_timeout
        if warmup_code is not None:
            self._config.warmup_code = warmup_code
        # Handle any additional kwargs
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
```

## Success Validation

### Must Pass (Critical)
- [ ] Sessions with warmup_code start successfully in <1s
- [ ] Warmup code executes and variables are available
- [ ] SessionPool accepts keyword arguments
- [ ] All existing 29 tests continue passing
- [ ] No new deadlocks or race conditions

### Test Cases

```python
# Test 1: Warmup Works
async def test_warmup_success():
    session = Session(warmup_code="test_var = 123")
    await asyncio.wait_for(session.start(), timeout=2.0)  # Must not timeout
    
    msg = ExecuteMessage(
        type="execute",
        id="test",
        timestamp=time.time(),
        code="print(test_var)",
        capture_source=False
    )
    
    output = []
    async for response in session.execute(msg):
        if response.type == MessageType.OUTPUT:
            output.append(response.data)
    
    assert "123" in "".join(output)

# Test 2: Pool Parameters Work
def test_pool_kwargs():
    pool = SessionPool(min_idle=2, max_sessions=5)  # Must not raise TypeError
    assert pool._config.min_idle == 2
    assert pool._config.max_sessions == 5
```

### Performance Validation
- Warmup execution time: <100ms for simple code
- No increase in memory usage
- No additional threads created

## Risk Mitigation Checklist

Before implementing:
- [ ] Review state machine transitions
- [ ] Verify _receive_loop is running before execute()
- [ ] Check that warmup_code doesn't contain blocking operations
- [ ] Ensure backward compatibility for existing SessionPool usage

During implementation:
- [ ] Add debug logging at state transitions
- [ ] Test with various warmup_code complexities
- [ ] Run existing test suite after each change

After implementation:
- [ ] Verify no deadlocks with 100 sequential sessions with warmup
- [ ] Stress test pool with concurrent acquisitions
- [ ] Document any behavioral changes

## Expected Outcomes

1. **Warmup Fix**: 
   - Sessions with warmup start in <1 second
   - Warmup variables accessible in subsequent executions
   - No impact on non-warmup sessions

2. **Pool Parameter Fix**:
   - Intuitive API: `SessionPool(min_size=N, max_size=M)`
   - Backward compatible with PoolConfig approach
   - Matches common Python pool patterns

## Notes on Architecture Preservation

The fixes preserve critical architectural decisions:
- Single-reader pattern (prevents v0.1 deadlocks)
- Message queue isolation (prevents response mixing)  
- State machine integrity (predictable behavior)
- Background task management (continuous message processing)

The warmup fix is essentially a one-line change to state ordering, proving that the infrastructure is complete and just needed correct sequencing.