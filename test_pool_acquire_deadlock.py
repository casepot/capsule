#!/usr/bin/env python3
"""Test to verify and debug SessionPool acquire deadlock"""

import asyncio
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.session.pool import SessionPool, PoolConfig


def show_thread_stacks():
    """Print all thread stack traces for debugging"""
    print("\n=== THREAD STACKS ===")
    for thread_id, frame in sys._current_frames().items():
        thread = threading.current_thread()
        print(f"\nThread {thread_id} ({thread.name}):")
        import traceback
        traceback.print_stack(frame)
    print("=== END STACKS ===\n")


async def test_pool_acquire_with_tracing():
    """Test pool acquire with detailed tracing"""
    print("Testing pool acquire for 3 sessions...")
    print(f"min_idle=2, max_sessions=3")
    
    # Patch the pool to add logging
    original_create_session = SessionPool._create_session
    
    async def traced_create_session(self):
        print(f"  [_create_session] Starting...")
        print(f"  [_create_session] About to call original method")
        result = await original_create_session(self)
        print(f"  [_create_session] Completed, session_id={result.session_id[:8]}")
        return result
    
    SessionPool._create_session = traced_create_session
    
    # Patch lock acquisition
    original_lock = asyncio.Lock
    
    class TracedLock(asyncio.Lock):
        def __init__(self):
            super().__init__()
            self._holder_stack = None
            
        async def __aenter__(self):
            import traceback
            stack = ''.join(traceback.format_stack()[:-1])
            
            if self.locked():
                print(f"  [LOCK] Waiting for lock (currently held by another coroutine)")
                print(f"  [LOCK] Current stack trying to acquire:\n{stack[-500:]}")
                
            result = await super().__aenter__()
            self._holder_stack = stack
            print(f"  [LOCK] Acquired")
            return result
            
        async def __aexit__(self, *args):
            print(f"  [LOCK] Released")
            self._holder_stack = None
            return await super().__aexit__(*args)
    
    # Create pool with traced lock
    pool = SessionPool(max_sessions=3, min_idle=2)
    pool._lock = TracedLock()
    
    print("\n1. Starting pool...")
    await pool.start()
    print("   Pool started (should have pre-warmed 2 sessions)")
    
    print("\n2. Acquiring first session...")
    session1 = await asyncio.wait_for(pool.acquire(), timeout=5.0)
    print(f"   Acquired session 1: {session1.session_id[:8]}")
    
    print("\n3. Acquiring second session...")
    session2 = await asyncio.wait_for(pool.acquire(), timeout=5.0)
    print(f"   Acquired session 2: {session2.session_id[:8]}")
    
    print("\n4. Acquiring third session (this may deadlock)...")
    try:
        # Use a shorter timeout to detect deadlock quickly
        session3 = await asyncio.wait_for(pool.acquire(), timeout=3.0)
        print(f"   ✓ Acquired session 3: {session3.session_id[:8]}")
        print("   NO DEADLOCK - hypothesis may be wrong")
    except asyncio.TimeoutError:
        print("   ✗ TIMEOUT acquiring third session - DEADLOCK CONFIRMED")
        print("\n   Checking for lock status...")
        if pool._lock.locked():
            print("   Lock is currently held!")
        else:
            print("   Lock is free (different issue)")
    
    print("\n5. Stopping pool...")
    await pool.stop()
    print("   Pool stopped")


async def test_simple_three_sessions():
    """Simple test without tracing"""
    print("\nSimple test: Acquiring 3 sessions from pool(max=3, min_idle=2)")
    
    pool = SessionPool(max_sessions=3, min_idle=2)
    await pool.start()
    
    sessions = []
    for i in range(3):
        print(f"  Acquiring session {i+1}...")
        try:
            session = await asyncio.wait_for(pool.acquire(), timeout=2.0)
            sessions.append(session)
            print(f"  ✓ Got session {i+1}")
        except asyncio.TimeoutError:
            print(f"  ✗ TIMEOUT on session {i+1}")
            break
    
    await pool.stop()
    
    if len(sessions) == 3:
        print("SUCCESS: All 3 sessions acquired")
    else:
        print(f"FAILED: Only got {len(sessions)} sessions")


async def main():
    """Run tests"""
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    print("="*60)
    print("Pool Acquire Deadlock Test")
    print("="*60)
    
    try:
        # First do simple test
        await test_simple_three_sessions()
        
        print("\n" + "="*60)
        
        # Then traced test
        await test_pool_acquire_with_tracing()
        
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("Test Complete")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())