# PyREPL3 Remaining Issues Summary

## Last Updated: 2025-08-25 (Session 2)

## Working Features ✅
1. **Basic session execution** - Sessions work perfectly with or without warmup
2. **Session with warmup code** - Warmup deadlock fixed, completes in <100ms
3. **Multiple sequential executions** - Can run multiple executions on same session
4. **Concurrent sessions** - Multiple sessions can run in parallel
5. **Output capture** - stdout/stderr properly captured and sent as messages
6. **Worker communication** - Execute messages are processed and results returned
7. **Direct subprocess communication** - Low-level framing and transport working
8. **SessionPool initialization** - Accepts both PoolConfig and keyword arguments

## Recently Fixed Issues ✅

### 1. ~~Session Warmup Deadlock~~ [FIXED]
**Status**: RESOLVED  
**Fix Applied**: 2025-08-25  
**Location**: `src/session/manager.py` lines 140-142

**Root Cause**:
- Session.start() held self._lock from lines 99-142
- While holding lock, called _warmup() which calls execute()
- execute() tried to acquire same lock → deadlock

**Solution**:
- Moved warmup execution outside lock scope
- State set to READY inside lock, warmup runs after lock released
- Preserves single-reader invariant

---

### 2. ~~SessionPool Parameter Mismatch~~ [FIXED]
**Status**: RESOLVED  
**Fix Applied**: 2025-08-25  
**Location**: `src/session/pool.py` lines 31-70

**Root Cause**:
- Constructor only accepted PoolConfig object
- No support for keyword arguments

**Solution**:
- Added keyword argument support for all config parameters
- Supports both APIs: `SessionPool(config)` and `SessionPool(min_idle=2, max_sessions=5)`
- Backward compatible with min_size/max_size aliases

---

## Current Issues 🟡

### 1. Pool Demo Timeout
**Status**: ACTIVE  
**Impact**: main.py pool demo doesn't complete  
**Location**: `main.py` pool demo section

**Symptoms**:
- Single session demo works perfectly
- Pool demo executes tasks 0 and 1, then hangs
- Timeout after ~15 seconds
- Task 2 never completes in asyncio.gather()

**Evidence**:
```
[Task 0] Task 0 running in session __main__
Task 0 result: 0
[Task 1] Task 1 running in session __main__
Task 1 result: 1
[Task 1] Result: 
[Task 0] Result: 
[15.091s] TIMEOUT: main() did not complete
```

**Hypothesis**: 
- Possible deadlock in pool acquire/release cycle
- Task 2 may be waiting indefinitely for session acquisition
- Pool lifecycle management issue unrelated to warmup fixes

**Workaround**: Use sessions directly without pool for now

---

## Non-Critical Issues ⚠️

### 1. Type Checking Errors
**Status**: Annoying but not blocking
**Count**: 13+ errors in basedpyright

Common issues:
- Message type narrowing problems
- Optional type handling
- AsyncIterator vs Coroutine confusion

### 2. Test Attribute Errors
**Status**: Tests pass but have errors
**Issue**: Some tests reference non-existent pool.size attribute

---

## Test Results Summary

| Test | Status | Time | Notes |
|------|--------|------|-------|
| Basic Session | ✅ PASS | 0.085s | Core functionality works |
| Session with Warmup | ✅ PASS | 0.084s | Fixed - no more deadlock |
| Pool Creation | ✅ PASS | - | Fixed - accepts kwargs |
| Multiple Executions | ✅ PASS | 0.088s | Sequential works |
| Concurrent Sessions | ✅ PASS | 0.094s | Parallel works |
| Pool Demo | 🟡 TIMEOUT | 15.0s | Task 2 blocks |

---

## Investigation Summary

### Session 1 (Earlier)
Fixed 8 critical issues:
1. Worker stdin/stdout initialization
2. AsyncIterator await bug
3. Protocol drain helper
4. Logger stderr configuration
5. Message routing
6. MessageTransport.start() call
7. FrameReader timeout
8. AsyncStdout task management

### Session 2 (Current)
Fixed 2 blocking issues:
1. **Session warmup deadlock** - Re-entrant lock issue resolved
2. **SessionPool parameter API** - Now accepts keyword arguments

---

## Priority for Next Session

1. **Investigate pool demo timeout** - Add logging to trace task 2 blockage
2. **Fix type checking errors** - Clean up type annotations
3. **Document API changes** - Update examples with new SessionPool syntax

---

## Architectural Notes

### Safeguards Maintained
- ✅ Single-reader invariant preserved
- ✅ Message queue isolation intact
- ✅ State machine integrity maintained
- ✅ Backward compatibility ensured

### Key Design Decisions
1. Warmup runs after READY state to avoid lock conflicts
2. SessionPool accepts both config objects and kwargs for flexibility
3. Lock scopes minimized to prevent deadlocks