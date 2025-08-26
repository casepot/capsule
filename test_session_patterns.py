#!/usr/bin/env python3
"""
Demonstration of good vs bad session usage patterns.
Shows why session reuse is critical for performance and stability.
"""

import asyncio
import sys
import time
import resource
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType


async def bad_pattern_new_session_per_execution():
    """BAD: Creates a new subprocess for each execution."""
    print("\n=== BAD PATTERN: New Session Per Execution ===")
    
    start_time = time.time()
    failures = 0
    
    # Get initial resource usage
    initial_fds = len(os.listdir('/proc/self/fd/')) if os.path.exists('/proc/self/fd/') else 0
    
    for i in range(20):  # Just 20 to avoid hanging
        try:
            # BAD: Creating new session (subprocess) each time
            session = Session()
            await asyncio.wait_for(session.start(), timeout=5.0)
            
            msg = ExecuteMessage(
                id=f"bad-{i}",
                timestamp=time.time(),
                code=f"print('test_{i}')"
            )
            
            has_output = False
            async for response in session.execute(msg, timeout=2.0):
                if response.type == MessageType.OUTPUT:
                    has_output = True
            
            await session.shutdown()
            
            if not has_output:
                failures += 1
                
        except Exception as e:
            failures += 1
            print(f"  Iteration {i}: FAILED - {e}")
    
    elapsed = time.time() - start_time
    
    print(f"  Time: {elapsed:.2f}s for 20 executions")
    print(f"  Rate: {20/elapsed:.1f} exec/sec")
    print(f"  Failures: {failures}")
    print(f"  ⚠️  Created 20 subprocesses (wasteful!)")
    
    return failures == 0


async def good_pattern_reuse_session():
    """GOOD: Reuses the same session for multiple executions."""
    print("\n=== GOOD PATTERN: Reuse Session ===")
    
    start_time = time.time()
    failures = 0
    
    # GOOD: Create session once
    session = Session()
    await session.start()
    
    try:
        for i in range(100):  # Can handle many more!
            msg = ExecuteMessage(
                id=f"good-{i}",
                timestamp=time.time(),
                code=f"print('test_{i}')"
            )
            
            has_output = False
            async for response in session.execute(msg, timeout=2.0):
                if response.type == MessageType.OUTPUT:
                    has_output = True
            
            if not has_output:
                failures += 1
                
    finally:
        await session.shutdown()
    
    elapsed = time.time() - start_time
    
    print(f"  Time: {elapsed:.2f}s for 100 executions")
    print(f"  Rate: {100/elapsed:.1f} exec/sec")
    print(f"  Failures: {failures}")
    print(f"  ✅ Used only 1 subprocess (efficient!)")
    
    return failures == 0


async def best_pattern_session_pool():
    """BEST: Uses a session pool for concurrent execution."""
    print("\n=== BEST PATTERN: Session Pool ===")
    
    from src.session.pool import SessionPool, PoolConfig
    
    start_time = time.time()
    
    # Configure pool
    config = PoolConfig(
        min_idle=2,
        max_sessions=5,
        warmup_code="import sys"
    )
    
    pool = SessionPool(config)
    await pool.start()
    
    async def execute_with_pool(exec_id: str):
        """Execute using pool."""
        session = await pool.acquire()
        try:
            msg = ExecuteMessage(
                id=exec_id,
                timestamp=time.time(),
                code=f"print('{exec_id}')"
            )
            
            has_output = False
            async for response in session.execute(msg, timeout=2.0):
                if response.type == MessageType.OUTPUT:
                    has_output = True
            
            return has_output
        finally:
            await pool.release(session)
    
    # Run many executions concurrently
    tasks = [
        execute_with_pool(f"pool-{i}")
        for i in range(50)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    failures = sum(1 for r in results if isinstance(r, Exception) or not r)
    elapsed = time.time() - start_time
    
    await pool.stop()
    
    print(f"  Time: {elapsed:.2f}s for 50 concurrent executions")
    print(f"  Rate: {50/elapsed:.1f} exec/sec")
    print(f"  Failures: {failures}")
    print(f"  ✅ Pool with 5 sessions handles concurrent load")
    
    return failures == 0


async def measure_resource_usage():
    """Measure resource usage of different patterns."""
    print("\n=== Resource Usage Comparison ===")
    
    import psutil
    process = psutil.Process()
    
    # Baseline
    baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
    baseline_fds = len(process.open_files()) + len(process.connections())
    
    print(f"  Baseline: {baseline_memory:.1f} MB, {baseline_fds} file descriptors")
    
    # Test single session
    session = Session()
    await session.start()
    
    session_memory = process.memory_info().rss / 1024 / 1024
    session_fds = len(process.open_files()) + len(process.connections())
    
    print(f"  1 Session: {session_memory:.1f} MB (+{session_memory-baseline_memory:.1f}), "
          f"{session_fds} FDs (+{session_fds-baseline_fds})")
    
    await session.shutdown()
    
    # Test multiple sessions (simulating bad pattern)
    sessions = []
    for i in range(5):
        s = Session()
        await s.start()
        sessions.append(s)
    
    multi_memory = process.memory_info().rss / 1024 / 1024
    multi_fds = len(process.open_files()) + len(process.connections())
    
    print(f"  5 Sessions: {multi_memory:.1f} MB (+{multi_memory-baseline_memory:.1f}), "
          f"{multi_fds} FDs (+{multi_fds-baseline_fds})")
    
    for s in sessions:
        await s.shutdown()
    
    print("\n  Key Insights:")
    print("  - Each session creates a subprocess (~5-10 MB)")
    print("  - Each session uses 2+ file descriptors (pipes)")
    print("  - Resource usage grows linearly with sessions")
    print("  - Session pools cap resource usage")


async def main():
    """Run pattern comparisons."""
    
    try:
        import os
        import psutil
    except ImportError:
        print("Note: Install psutil for detailed resource metrics")
        print("  pip install psutil")
    
    print("=" * 60)
    print("Session Usage Patterns Comparison")
    print("=" * 60)
    
    # Run pattern tests with timeouts
    tests = [
        ("Bad Pattern", bad_pattern_new_session_per_execution, 30.0),
        ("Good Pattern", good_pattern_reuse_session, 10.0),
        ("Best Pattern", best_pattern_session_pool, 15.0),
    ]
    
    results = []
    for name, test_func, timeout in tests:
        try:
            result = await asyncio.wait_for(test_func(), timeout=timeout)
            results.append((name, result))
        except asyncio.TimeoutError:
            print(f"\n  ⏱️  {name} timed out after {timeout}s")
            results.append((name, False))
        except Exception as e:
            print(f"\n  ❌ {name} failed: {e}")
            results.append((name, False))
    
    # Resource usage comparison
    try:
        await measure_resource_usage()
    except:
        print("\n(Resource measurement skipped)")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{name:20s}: {status}")
    
    print("\nRecommendations:")
    print("1. ALWAYS reuse sessions for multiple executions")
    print("2. Use SessionPool for concurrent workloads")
    print("3. Set reasonable pool limits (max_sessions)")
    print("4. Monitor resource usage in production")
    print("5. Implement health checks and recovery")


if __name__ == "__main__":
    import os
    asyncio.run(main())