#!/usr/bin/env python3
"""
Stress test for SessionPool to ensure no deadlocks under high concurrency.
Tests the fix for the acquire() method deadlock issue.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session.pool import SessionPool, PoolConfig
from src.protocol.messages import ExecuteMessage, MessageType


async def test_high_concurrency():
    """Test with many concurrent acquisitions."""
    print("\n=== Test: High concurrency (20 tasks, 10 max sessions) ===")
    
    config = PoolConfig(
        min_idle=0,  # Start with no pre-warmed sessions
        max_sessions=10,
        warmup_code="x = 1"
    )
    
    pool = SessionPool(config)
    await pool.start()
    
    print(f"Pool started with max_sessions={config.max_sessions}")
    
    async def acquire_and_release(task_id: int):
        """Acquire, execute, and release a session."""
        try:
            session = await asyncio.wait_for(pool.acquire(), timeout=10.0)
            print(f"[Task {task_id:2d}] Acquired session")
            
            # Execute simple code
            code = f"result = {task_id}"
            message = ExecuteMessage(
                id=f"stress-{task_id}",
                timestamp=time.time(),
                code=code
            )
            
            async for msg in session.execute(message):
                pass  # Just consume the messages
            
            await pool.release(session)
            print(f"[Task {task_id:2d}] Released session")
            return f"Task {task_id} completed"
            
        except asyncio.TimeoutError:
            print(f"[Task {task_id:2d}] ❌ TIMEOUT!")
            return None
    
    # Create more tasks than pool capacity
    tasks = []
    for i in range(20):  # 20 tasks, but only 10 max sessions
        tasks.append(acquire_and_release(i))
    
    print(f"\nStarting {len(tasks)} concurrent tasks...")
    start_time = time.time()
    
    # Should handle queueing without deadlock
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    elapsed = time.time() - start_time
    successful = len([r for r in results if r and not isinstance(r, Exception)])
    
    print(f"\nCompleted in {elapsed:.2f}s")
    print(f"Successful: {successful}/{len(tasks)}")
    
    assert successful == 20, f"Expected 20 successful tasks, got {successful}"
    assert elapsed < 20.0, f"Should complete quickly, took {elapsed:.2f}s"
    
    await pool.stop()
    print("✓ High concurrency test passed")


async def test_no_double_creation():
    """Ensure no sessions created beyond max."""
    print("\n=== Test: No double creation beyond max_sessions ===")
    
    config = PoolConfig(
        min_idle=0,
        max_sessions=3,
        warmup_code=None
    )
    
    pool = SessionPool(config)
    await pool.start()
    
    print(f"Pool started with max_sessions={config.max_sessions}")
    
    # Bombard with acquisitions
    async def try_acquire(task_id: int):
        try:
            session = await asyncio.wait_for(pool.acquire(), timeout=0.5)
            await asyncio.sleep(0.1)  # Hold the session briefly
            await pool.release(session)
            return session
        except asyncio.TimeoutError:
            return None
    
    tasks = [try_acquire(i) for i in range(10)]
    sessions = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Check pool state
    metrics = pool.get_metrics()
    assert metrics.total_sessions <= 3, f"Should have max 3 sessions, got {metrics.total_sessions}"
    
    successful = len([s for s in sessions if s and not isinstance(s, Exception)])
    print(f"Acquired {successful} sessions out of 10 attempts")
    print(f"Total sessions created: {metrics.sessions_created}")
    assert metrics.sessions_created <= 3, f"Should create max 3 sessions, created {metrics.sessions_created}"
    
    await pool.stop()
    print("✓ No double creation test passed")


async def test_acquisition_performance():
    """Ensure fix doesn't degrade performance."""
    print("\n=== Test: Acquisition performance ===")
    
    config = PoolConfig(
        min_idle=2,
        max_sessions=5,
        warmup_code="x = 1",
        pre_warm_on_start=True
    )
    
    pool = SessionPool(config)
    await pool.start()
    
    print(f"Pool started with min_idle={config.min_idle}, max={config.max_sessions}")
    
    # Measure concurrent acquisition time
    async def timed_acquire(task_id: int):
        start = time.time()
        session = await pool.acquire()
        elapsed = time.time() - start
        await pool.release(session)
        return elapsed
    
    # First round - should use pre-warmed sessions
    print("\nRound 1: Using pre-warmed sessions...")
    times1 = await asyncio.gather(
        timed_acquire(0),
        timed_acquire(1)
    )
    
    avg1 = sum(times1) / len(times1)
    print(f"Average acquisition time (warm): {avg1*1000:.2f}ms")
    assert avg1 < 0.1, f"Warm acquisition should be < 100ms, got {avg1*1000:.2f}ms"
    
    # Second round - will need to create new sessions
    print("\nRound 2: Creating new sessions...")
    times2 = await asyncio.gather(
        timed_acquire(2),
        timed_acquire(3),
        timed_acquire(4)
    )
    
    avg2 = sum(times2) / len(times2)
    print(f"Average acquisition time (with creation): {avg2*1000:.2f}ms")
    assert avg2 < 1.0, f"Creation should be < 1s, got {avg2:.2f}s"
    
    await pool.stop()
    print("✓ Performance test passed")


async def test_race_condition_prevention():
    """Test that placeholder mechanism prevents race conditions."""
    print("\n=== Test: Race condition prevention ===")
    
    config = PoolConfig(
        min_idle=0,
        max_sessions=5,
        warmup_code=None
    )
    
    pool = SessionPool(config)
    await pool.start()
    
    print(f"Pool started with max_sessions={config.max_sessions}")
    
    # All tasks try to acquire at exactly the same time
    barrier = asyncio.Barrier(10)
    
    async def synchronized_acquire(task_id: int):
        await barrier.wait()  # All tasks start together
        try:
            session = await asyncio.wait_for(pool.acquire(), timeout=5.0)
            print(f"[Task {task_id}] Acquired")
            await asyncio.sleep(0.05)  # Brief work
            await pool.release(session)
            return True
        except asyncio.TimeoutError:
            return False
    
    # Launch 10 tasks that all try to acquire simultaneously
    tasks = [synchronized_acquire(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    
    successful = sum(results)
    print(f"\n{successful}/10 tasks completed successfully")
    
    # Check that we didn't create more than max_sessions
    metrics = pool.get_metrics()
    assert metrics.total_sessions <= 5, f"Should have max 5 sessions, got {metrics.total_sessions}"
    assert metrics.sessions_created <= 5, f"Should create max 5 sessions, created {metrics.sessions_created}"
    
    await pool.stop()
    print("✓ Race condition prevention test passed")


async def main():
    """Run all stress tests."""
    print("=" * 60)
    print("SESSION POOL STRESS TESTS")
    print("=" * 60)
    
    # Run all tests
    await test_high_concurrency()
    await test_no_double_creation()
    await test_acquisition_performance()
    await test_race_condition_prevention()
    
    print("\n" + "=" * 60)
    print("✅ ALL STRESS TESTS PASSED")
    print("The SessionPool deadlock has been successfully fixed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())