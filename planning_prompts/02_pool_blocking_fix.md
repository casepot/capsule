# Pool Blocking Fix Planning Prompt

## Your Mission

You are tasked with fixing the SessionPool deadlock where the third concurrent task in asyncio.gather() blocks forever. The bug has been identified: the `acquire()` method holds a lock while awaiting subprocess creation, causing deadlock when multiple tasks compete for sessions.

This fix is critical to PyREPL3's vision as a **Subprocess-Isolated Execution Service (SIES)** - without concurrent session support, the managed stateful process pool cannot function.

## Context

### Historical Context (Problem Archaeology)

#### Previous Attempts and Failures

1. **Session Warmup Deadlock (FIXED in Session 2)**
   - What: Session.start() held lock while calling _warmup() which calls execute()
   - Why Failed: execute() tried to acquire same lock → deadlock
   - Fix Applied: Moved warmup execution outside lock scope (lines 140-142)
   - Lesson: Never await operations that need the same lock you're holding

2. **pyrepl2 SessionPool Deadlock**
   - What: Pool pre-warming during start() with lock held
   - Why Failed: _ensure_min_idle_sessions held lock while awaiting session creation
   - Pattern: Parent holds lock → creates child tasks → waits → children need lock → deadlock
   - Key Learning: Create tasks inside lock, await outside lock

3. **Parameter Mismatch (FIXED in Session 2)**
   - What: SessionPool only accepted PoolConfig object
   - Fix Applied: Added keyword argument support
   - Now Works: `SessionPool(min_idle=2, max_sessions=5)`

#### Test Evidence
```python
# From test_pool_blocking.py results:
[Task 0] Acquired session in 0.00s  # ✅ Works
[Task 1] Acquired session in 0.00s  # ✅ Works
[Task 2] ❌ TIMEOUT during acquisition!  # Third task always fails

# But sequential works perfectly:
[Sequential 0] Released  # ✅
[Sequential 1] Released  # ✅
[Sequential 2] Released  # ✅ All three work sequentially
```

### Existing Infrastructure (Architecture Recognition)

#### Working Components

1. **SessionPool** (src/session/pool.py)
   - Lines 71-72: Uses asyncio.Queue for idle sessions
   - Lines 73: Set for active sessions
   - Line 74: Lock for synchronization
   - Lines 91-94: Background tasks for warmup and health checks

2. **Session Lifecycle**
   - Session.start() now completes without deadlock
   - Warmup executes successfully after READY state
   - Sequential acquire/release works perfectly

3. **Background Tasks**
   - `_warmup_loop()`: Ensures minimum idle sessions
   - `_health_check_loop()`: Monitors session health

#### Code Analysis

1. **ensure_min_sessions() method** (lines 344-378) ✅ CORRECT
   - Already implements lock-free pattern correctly
   - Creates tasks inside lock, awaits outside
   - Not the source of the deadlock

2. **acquire() method** (lines 127-186) ❌ BUG LOCATION
   - Line 173-178: Holds lock while creating session
   - Comment says "without holding lock" but code is inside lock block!
   - Classic await-while-holding-lock deadlock

3. **The Actual Bug** (src/session/pool.py:173-178)
```python
async with self._lock:
    total_sessions = len(self._all_sessions)
    
    if total_sessions < self._config.max_sessions:
        # Create new session without holding lock  # <- MISLEADING COMMENT
        session = await self._create_session()      # <- BUG: STILL HOLDING LOCK!
```

### Problem Analysis

#### Why It Deadlocks
1. **Task 0**: Gets pre-warmed session from queue (no lock needed)
2. **Task 1**: Gets second pre-warmed session from queue (no lock needed)
3. **Task 2**: Queue empty, needs to create session
   - Acquires lock at line 173
   - Calls `_create_session()` at line 178 (STILL HOLDING LOCK)
   - `_create_session()` spawns subprocess (100ms+ operation)
   - Meanwhile, warmup task or other operations need lock
   - Deadlock!

#### Why Sequential Works
- Each task completes and releases before next starts
- No lock contention between concurrent operations
- Sessions properly returned to idle queue

#### Subprocess Creation Cost
Session creation involves:
- `asyncio.create_subprocess_exec()` - OS process spawn
- Protocol handshake - READY message exchange
- Warmup code execution - imports, setup
- This takes 100-500ms - far too long to hold a lock!

## Constraints

### Non-Negotiable Requirements
1. **Warmup Must Work**: Recently fixed warmup functionality cannot regress
2. **No Breaking Changes**: All existing sequential tests must pass
3. **Concurrency Support**: Pool must support N concurrent acquisitions (up to max_sessions)
4. **Background Tasks**: Health check and warmup loops must continue functioning

### Risks to Avoid

#### Risk 1: Reintroducing Warmup Deadlock
- **Probability**: Medium if lock scoping changed carelessly
- **Impact**: Critical (pool unusable)
- **Scenario**: Modifying lock usage breaks the warmup fix
- **Mitigation**: Keep warmup execution outside lock scope

#### Risk 2: Creating New Race Conditions
- **Probability**: High when fixing concurrency issues
- **Impact**: Major (intermittent failures)
- **Scenario**: Multiple tasks modifying pool state simultaneously
- **Mitigation**: Careful lock scoping, atomic operations

#### Risk 3: Resource Leaks
- **Probability**: Medium
- **Impact**: Major (sessions orphaned)
- **Scenario**: Sessions not properly returned to pool on error
- **Mitigation**: Ensure finally blocks for all acquire/release pairs

## Planning Approach

### Debugging Strategy (Phase 1)

1. **Add Comprehensive Logging**
```python
# In acquire() method
logger.info("Acquire attempt", 
    task_name=asyncio.current_task().get_name(),
    idle_count=self._idle_sessions.qsize(),
    active_count=len(self._active_sessions),
    total_count=len(self._all_sessions))

# In ensure_min_sessions()
logger.info("Lock acquisition attempt in ensure_min")
async with self._lock:
    logger.info("Lock acquired in ensure_min")
# Log when lock released
```

2. **Trace Lock Ownership**
   - Log every lock acquisition/release
   - Include task name and timestamp
   - Identify where Task 2 blocks

3. **Monitor Queue States**
   - Log idle queue size before/after operations
   - Track active session transitions
   - Verify sessions are returned properly

### The Fix: Lock-Free Session Creation in acquire()

#### The Correct Pattern
**Philosophy**: Never await expensive operations while holding locks
**Key Insight**: Session creation is subprocess spawning - inherently slow

**Implementation**:
```python
async def acquire(self, timeout: Optional[float] = None) -> Session:
    """Fixed version with lock-free session creation."""
    # ... existing code ...
    
    while not self._shutdown:
        # Try to get idle session (unchanged)
        try:
            session = self._idle_sessions.get_nowait()
            if session.is_alive:
                async with self._lock:
                    self._active_sessions.add(session)
                return session
            else:
                await self._remove_session(session)
        except asyncio.QueueEmpty:
            pass
        
        # Check if we can create new session (FIXED)
        should_create = False
        async with self._lock:
            total_sessions = len(self._all_sessions)
            if total_sessions < self._config.max_sessions:
                should_create = True
                # Reserve slot to prevent race condition
                placeholder_id = f"creating-{uuid.uuid4()}"
                self._all_sessions[placeholder_id] = None
        
        if should_create:
            # Create session OUTSIDE lock
            try:
                session = await self._create_session()
                
                # Add to pool with lock
                async with self._lock:
                    # Remove placeholder
                    del self._all_sessions[placeholder_id]
                    # Add real session
                    self._all_sessions[session.session_id] = session
                    self._active_sessions.add(session)
                
                return session
                
            except Exception as e:
                # Clean up placeholder on error
                async with self._lock:
                    self._all_sessions.pop(placeholder_id, None)
                raise
        
        # Wait before retry (with timeout check)
        # ... rest of method ...
```

#### Why This Works
1. **Lock only for state inspection**: Check capacity, reserve slot
2. **Expensive operations outside lock**: Subprocess creation happens freely
3. **Atomic updates**: Lock only for quick dictionary updates
4. **Race condition prevention**: Placeholder prevents double-creation

#### Alternative: Async Task Pattern
Similar to what ensure_min_sessions() already does correctly:
```python
# Inside lock: create task
task = asyncio.create_task(self._create_session())

# Outside lock: await task
session = await task
```

### Edge Cases to Consider

1. **Rapid acquisition/release cycles**: Ensure placeholders don't accumulate
2. **Session creation failures**: Clean up placeholders properly
3. **Shutdown during creation**: Handle gracefully
4. **Timeout during creation**: Don't leave dangling placeholders

### Important Notes

- **Don't optimize prematurely**: Subprocess creation is inherently 100-500ms
- **Placeholder cleanup is critical**: Always use try/finally or except blocks
- **The comment was prophetic**: Developer knew it should be "without holding lock"
- **ensure_min_sessions() is already correct**: Don't "fix" what isn't broken

## Implementation Guide

### Phase 1: Verify the Bug (10% effort)

1. **Confirm Bug Location** (src/session/pool.py:173-178)
```python
# Look for this pattern in acquire():
async with self._lock:
    if total_sessions < self._config.max_sessions:
        session = await self._create_session()  # BUG HERE
```

2. **Run Existing Test** 
```bash
python test_reproductions/test_pool_blocking.py
# Confirm Task 2 times out
```

### Phase 2: Implement the Fix (30% effort)

**File: src/session/pool.py** (lines 173-186 in acquire() method)

Replace the buggy section:
```python
# OLD (BUGGY) CODE:
async with self._lock:
    total_sessions = len(self._all_sessions)
    
    if total_sessions < self._config.max_sessions:
        # Create new session without holding lock  # WRONG!
        session = await self._create_session()      # BUG: HOLDS LOCK
```

With the fixed version:
```python
# NEW (FIXED) CODE:
should_create = False
placeholder_id = None

async with self._lock:
    total_sessions = len(self._all_sessions)
    
    if total_sessions < self._config.max_sessions:
        should_create = True
        # Reserve slot to prevent race condition
        placeholder_id = f"creating-{uuid.uuid4()}"
        self._all_sessions[placeholder_id] = None

if should_create:
    # Create session OUTSIDE lock (actually true now!)
    try:
        session = await self._create_session()
        
        async with self._lock:
            # Swap placeholder for real session
            if placeholder_id in self._all_sessions:
                del self._all_sessions[placeholder_id]
            self._all_sessions[session.session_id] = session
            self._active_sessions.add(session)
        
        # Update metrics and return
        self._metrics.acquisition_success += 1
        self._metrics.pool_misses += 1
        return session
        
    except Exception as e:
        # Clean up placeholder on error
        async with self._lock:
            if placeholder_id in self._all_sessions:
                del self._all_sessions[placeholder_id]
        logger.error(f"Failed to create session: {e}")
        # Continue loop to retry or timeout
```

### Phase 3: Validation (30% effort)

1. **Run Original Failing Test**
```bash
python test_reproductions/test_pool_blocking.py
# Should now show all 3 tasks succeeding
```

2. **Stress Test with More Concurrency**
```python
async def test_high_concurrency():
    """Test with many concurrent acquisitions."""
    pool = SessionPool(min_idle=0, max_sessions=10)
    await pool.start()
    
    # Create more tasks than pool capacity
    tasks = []
    for i in range(20):  # 20 tasks, 10 max sessions
        tasks.append(acquire_and_release(pool, i))
    
    # Should handle queueing without deadlock
    results = await asyncio.gather(*tasks)
    assert len(results) == 20
```

3. **Race Condition Test**
```python
async def test_no_double_creation():
    """Ensure no sessions created beyond max."""
    pool = SessionPool(min_idle=0, max_sessions=3)
    await pool.start()
    
    # Bombard with acquisitions
    tasks = [pool.acquire() for _ in range(10)]
    sessions = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Check pool state
    assert len(pool._all_sessions) <= 3
    assert len([s for s in sessions if not isinstance(s, Exception)]) == 3
```

4. **Performance Verification**
```python
async def test_acquisition_performance():
    """Ensure fix doesn't degrade performance."""
    pool = SessionPool(min_idle=2, max_sessions=5)
    await pool.start()
    
    start = time.time()
    sessions = await asyncio.gather(
        pool.acquire(),
        pool.acquire(), 
        pool.acquire()
    )
    elapsed = time.time() - start
    
    # Should complete quickly (< 1s even with session creation)
    assert elapsed < 1.0
    assert all(s.is_alive for s in sessions)
```

## Output Requirements

Your planning deliverable must include:

1. **Root Cause Analysis**: 
   - Specific identification of deadlock location
   - Lock contention diagram
   - Task blocking sequence

2. **Implementation Plan**:
   - Debug logging additions (exact locations)
   - Fix implementation (complete code)
   - Order of changes to preserve working features

3. **Testing Strategy**:
   - Debug test to identify issue
   - Fix verification test
   - Regression test suite

4. **Risk Mitigation**:
   - How warmup functionality is preserved
   - How race conditions are avoided
   - Rollback plan if fix fails

## Success Validation

### Functional Tests
| Requirement | Test Case | Expected Result | Pass Criteria |
|-------------|-----------|-----------------|---------------|
| Concurrent acquisition | 3 tasks in gather() | All acquire | No timeout |
| Scale test | 5 tasks in gather() | All acquire | Complete < 5s |
| Pool limits | Request > max_sessions | Wait queue works | No deadlock |
| Warmup works | Pool with warmup_code | Starts successfully | < 2s startup |

### Performance Metrics
- Session acquisition: < 100ms when available
- New session creation: < 500ms
- Concurrent acquisition: Linear scaling up to max_sessions

### Debug Validation
```python
# No lock held while awaiting
assert "Lock held during await" not in logs

# All tasks complete
assert all(task.done() for task in tasks)

# No orphaned sessions
assert len(active_sessions) + idle_queue.qsize() == len(all_sessions)
```

## Why This Fix Matters

### Architectural Significance

PyREPL3 implements a **Subprocess-Isolated Execution Service (SIES)** pattern. Without concurrent session support:
- No parallel execution for multiple users
- API layer cannot serve concurrent requests
- Session pooling provides no benefit
- The entire "managed stateful process pool" vision fails

### Performance Impact

With this fix:
- **Before**: Only 2 concurrent sessions (pre-warmed), 3rd blocks forever
- **After**: N concurrent sessions up to max_sessions limit
- **Acquisition time**: < 100ms for warm sessions, < 500ms with creation
- **Throughput**: 10-100x improvement for concurrent workloads

### Downstream Benefits

This fix unblocks:
1. **API Implementation**: WebSocket/REST can handle multiple clients
2. **Notebook Support**: Multiple cells executing in parallel
3. **Production Deployment**: Multi-user environments become possible
4. **Resource Management**: Pool can efficiently manage subprocess lifecycle

## Expected Outcome

After implementing this fix:
1. ✅ **Concurrent acquisition works**: N tasks can acquire up to max_sessions
2. ✅ **No deadlocks**: Lock-free pattern prevents blocking
3. ✅ **Race-free**: Placeholder mechanism prevents double-creation
4. ✅ **Performance maintained**: < 100ms warm, < 500ms with creation
5. ✅ **Existing features preserved**: Warmup, health checks, metrics all work
6. ✅ **Production ready**: Can handle high concurrency workloads

The pool will finally fulfill its role as the foundation of PyREPL3's session-oriented RPC architecture.