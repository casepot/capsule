#!/usr/bin/env python3
"""Verify the pool deadlock by checking lock state"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.session.pool import SessionPool


async def test_deadlock_verification():
    """Test that clearly shows the deadlock"""
    print("Deadlock Verification Test")
    print("="*50)
    
    # Monkey-patch to trace the issue
    original_create = SessionPool._create_session
    original_acquire = SessionPool.acquire
    
    async def traced_create(self):
        print("[_create_session] Called - trying to acquire lock at line 280...")
        if self._lock.locked():
            print("[_create_session] ⚠️  LOCK IS ALREADY HELD! This will deadlock!")
        result = await original_create(self)
        print("[_create_session] Completed")
        return result
    
    async def traced_acquire(self, timeout=None):
        """Traced acquire that shows lock status"""
        # Copy first part of acquire logic
        import time
        start_time = time.time()
        self._metrics.acquisition_attempts += 1
        deadline = time.time() + timeout if timeout else None
        
        while not self._shutdown:
            # Try to get idle session
            try:
                session = self._idle_sessions.get_nowait()
                if session.is_alive:
                    async with self._lock:
                        self._active_sessions.add(session)
                    print(f"[acquire] Got idle session: {session.session_id[:8]}")
                    return session
                else:
                    await self._remove_session(session)
            except asyncio.QueueEmpty:
                pass
            
            # Check if we can create new session
            print("[acquire] No idle sessions, checking if can create new...")
            async with self._lock:
                print("[acquire] Lock acquired at line 173")
                total_sessions = len(self._all_sessions)
                print(f"[acquire] Total sessions: {total_sessions}, max: {self._config.max_sessions}")
                
                if total_sessions < self._config.max_sessions:
                    print("[acquire] Can create new session")
                    print("[acquire] ⚠️  ABOUT TO CALL _create_session() WHILE HOLDING LOCK!")
                    # THIS IS THE BUG - calling _create_session while holding lock
                    session = await self._create_session()  # DEADLOCK HERE!
                    
                    async with self._lock:  # This will never execute
                        self._active_sessions.add(session)
                    
                    return session
            
            # Wait logic...
            if deadline and deadline - time.time() <= 0:
                raise TimeoutError("Session acquisition timeout")
            
            print("[acquire] Waiting for session to become available...")
            break  # Exit for test
        
        raise RuntimeError("Pool is shutting down")
    
    SessionPool._create_session = traced_create
    SessionPool.acquire = traced_acquire
    
    # Run test
    pool = SessionPool(max_sessions=3, min_idle=2)
    await pool.start()
    
    print("\nPool started with 2 pre-warmed sessions")
    print("-"*50)
    
    # Get the two pre-warmed sessions
    s1 = await pool.acquire()
    print(f"✓ Got session 1: {s1.session_id[:8]}")
    
    s2 = await pool.acquire()
    print(f"✓ Got session 2: {s2.session_id[:8]}")
    
    print("\n" + "-"*50)
    print("Now acquiring 3rd session (will trigger on-demand creation)...")
    print("-"*50)
    
    try:
        s3 = await asyncio.wait_for(pool.acquire(), timeout=2.0)
        print(f"✓ Got session 3: {s3.session_id[:8]}")
    except asyncio.TimeoutError:
        print("\n❌ DEADLOCK CONFIRMED!")
        print("   acquire() holds lock at line 173-178")
        print("   _create_session() needs lock at line 280")
        print("   Result: Infinite wait")
    
    await pool.stop()


async def main():
    """Run test"""
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    await test_deadlock_verification()


if __name__ == "__main__":
    asyncio.run(main())