# Concurrent Sessions Deadlock Fix

## Problem
Integration test `test_concurrent_sessions()` hangs when acquiring a third session from a pool with `max_sessions=3` and `min_idle=2`.

## Root Cause  
**Deadlock in SessionPool.acquire()** at src/session/pool.py:

```python
# Line 173-178: DEADLOCK!
async with self._lock:
    total_sessions = len(self._all_sessions)
    
    if total_sessions < self._config.max_sessions:
        # THIS CALLS _create_session() WHILE HOLDING LOCK!
        session = await self._create_session()  # Line 178
```

The `_create_session()` method tries to acquire the same lock at line 280:
```python
async def _create_session(self) -> Session:
    # ...
    async with self._lock:  # Line 280 - WAITS FOR LOCK WE ALREADY HOLD!
        self._all_sessions[session.session_id] = session
```

## Why It Only Affects the Third Session
- Sessions 1-2: Pre-warmed during pool startup (no deadlock path)
- Session 3: Created on-demand via acquire() → hits deadlock

## Fix
Move the `_create_session()` call outside the lock scope:

```python
# Check if we can create new session
async with self._lock:
    total_sessions = len(self._all_sessions)
    can_create = total_sessions < self._config.max_sessions

if can_create:
    # Create new session WITHOUT holding lock
    session = await self._create_session()
    
    async with self._lock:
        self._active_sessions.add(session)
    
    # ... rest of the code
```

## Verification
After fix, `test_concurrent_sessions()`:
1. Successfully acquires all 3 sessions ✓
2. Executes code on all sessions concurrently ✓
3. Completes without timeout ✓

## Test Results
```
Testing concurrent sessions...
  ✓ All sessions executed correctly with normalized types
```

All integration tests now pass successfully!