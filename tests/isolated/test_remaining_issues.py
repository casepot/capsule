#!/usr/bin/env python3
"""Systematic testing to identify remaining issues."""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.session.manager import Session
from src.session.pool import SessionPool
from src.protocol.messages import ExecuteMessage

# Test results tracker
results = []

async def test_with_timeout(name: str, test_func, timeout: float = 5.0):
    """Run a test with timeout and track results."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    
    start_time = time.time()
    try:
        result = await asyncio.wait_for(test_func(), timeout=timeout)
        elapsed = time.time() - start_time
        results.append({
            "test": name,
            "status": "PASS" if result else "FAIL",
            "time": f"{elapsed:.3f}s",
            "error": None
        })
        print(f"✓ {name} - {'PASSED' if result else 'FAILED'} in {elapsed:.3f}s")
        return result
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        results.append({
            "test": name,
            "status": "TIMEOUT",
            "time": f"{elapsed:.3f}s",
            "error": f"Timed out after {timeout}s"
        })
        print(f"✗ {name} - TIMEOUT after {timeout}s")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        results.append({
            "test": name,
            "status": "ERROR",
            "time": f"{elapsed:.3f}s",
            "error": str(e)
        })
        print(f"✗ {name} - ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_1_basic_session():
    """Test basic session without warmup."""
    print("Creating session...")
    session = Session()
    
    print("Starting session...")
    await session.start()
    
    print("Executing simple code...")
    msg = ExecuteMessage(
        type="execute",
        id="test1",
        timestamp=time.time(),
        code="result = 1 + 1",
        capture_source=False
    )
    
    messages = []
    async for message in session.execute(msg):
        messages.append(message)
        print(f"  Received: {message.type}")
    
    print(f"Total messages: {len(messages)}")
    
    print("Terminating...")
    await session.terminate()
    
    return len(messages) > 0


async def test_2_session_with_warmup():
    """Test session with warmup code."""
    print("Creating session with warmup code...")
    warmup_code = "import sys\nwarmup_var = 42"
    session = Session(warmup_code=warmup_code)
    
    print("Starting session (includes warmup)...")
    await session.start()
    
    print("Session state after start:", session.state)
    
    print("Executing code that uses warmup...")
    msg = ExecuteMessage(
        type="execute",
        id="test2",
        timestamp=time.time(),
        code="print(f'Warmup var: {warmup_var}')",
        capture_source=False
    )
    
    messages = []
    async for message in session.execute(msg):
        messages.append(message)
        print(f"  Received: {message.type}")
        if message.type == "output":
            print(f"    Data: {message.data}")
    
    print(f"Total messages: {len(messages)}")
    
    print("Terminating...")
    await session.terminate()
    
    return len(messages) > 0


async def test_3_pool_creation():
    """Test session pool creation."""
    print("Creating pool with min_size=1, max_size=2...")
    pool = SessionPool(min_size=1, max_size=2)
    
    print("Starting pool...")
    await pool.start()
    
    print(f"Pool size: {pool.size}")
    print(f"Available sessions: {pool.available}")
    
    print("Stopping pool...")
    await pool.stop()
    
    return pool.size >= 1


async def test_4_pool_with_warmup():
    """Test session pool with warmup code."""
    print("Creating pool with warmup code...")
    warmup_code = "pool_var = 'initialized'"
    pool = SessionPool(
        min_size=1, 
        max_size=2,
        warmup_code=warmup_code
    )
    
    print("Starting pool (should pre-warm sessions)...")
    await pool.start()
    
    print(f"Pool size after start: {pool.size}")
    print(f"Available sessions: {pool.available}")
    
    if pool.available > 0:
        print("Acquiring session...")
        session = await pool.acquire()
        
        print("Executing code using warmup...")
        msg = ExecuteMessage(
            type="execute",
            id="test4",
            timestamp=time.time(),
            code="print(f'Pool var: {pool_var}')",
            capture_source=False
        )
        
        messages = []
        async for message in session.execute(msg):
            messages.append(message)
            print(f"  Received: {message.type}")
            if message.type == "output":
                print(f"    Data: {message.data}")
        
        print("Releasing session...")
        await pool.release(session)
        
        success = len(messages) > 0
    else:
        print("No sessions available!")
        success = False
    
    print("Stopping pool...")
    await pool.stop()
    
    return success


async def test_5_multiple_executions():
    """Test multiple sequential executions on same session."""
    print("Creating session...")
    session = Session()
    
    print("Starting session...")
    await session.start()
    
    success = True
    for i in range(3):
        print(f"\nExecution {i+1}...")
        msg = ExecuteMessage(
            type="execute",
            id=f"test5_{i}",
            timestamp=time.time(),
            code=f"result = {i} * 2\nprint(f'Result {i}: {{result}}')",
            capture_source=False
        )
        
        messages = []
        async for message in session.execute(msg):
            messages.append(message)
            print(f"  Received: {message.type}")
        
        if len(messages) == 0:
            print(f"  ERROR: No messages received for execution {i+1}")
            success = False
    
    print("Terminating...")
    await session.terminate()
    
    return success


async def test_6_concurrent_sessions():
    """Test multiple sessions running concurrently."""
    print("Creating 3 sessions...")
    sessions = [Session() for _ in range(3)]
    
    print("Starting all sessions...")
    await asyncio.gather(*[s.start() for s in sessions])
    
    print("Running concurrent executions...")
    
    async def execute_on_session(session, idx):
        msg = ExecuteMessage(
            type="execute",
            id=f"test6_{idx}",
            timestamp=time.time(),
            code=f"print('Session {idx}')",
            capture_source=False
        )
        
        messages = []
        async for message in session.execute(msg):
            messages.append(message)
        
        return len(messages) > 0
    
    results = await asyncio.gather(*[
        execute_on_session(sessions[i], i) 
        for i in range(len(sessions))
    ])
    
    print(f"Results: {results}")
    
    print("Terminating all sessions...")
    await asyncio.gather(*[s.terminate() for s in sessions])
    
    return all(results)


async def test_7_pool_concurrent_acquire():
    """Test concurrent session acquisition from pool."""
    print("Creating pool with min_size=2, max_size=3...")
    pool = SessionPool(min_size=2, max_size=3)
    
    print("Starting pool...")
    await pool.start()
    
    print(f"Pool size: {pool.size}, available: {pool.available}")
    
    print("Acquiring 2 sessions concurrently...")
    
    async def acquire_and_execute(pool, idx):
        print(f"  Task {idx}: Acquiring...")
        session = await pool.acquire()
        print(f"  Task {idx}: Acquired session")
        
        msg = ExecuteMessage(
            type="execute",
            id=f"test7_{idx}",
            timestamp=time.time(),
            code=f"result = {idx}",
            capture_source=False
        )
        
        messages = []
        async for message in session.execute(msg):
            messages.append(message)
        
        print(f"  Task {idx}: Releasing...")
        await pool.release(session)
        
        return len(messages) > 0
    
    results = await asyncio.gather(*[
        acquire_and_execute(pool, i) for i in range(2)
    ])
    
    print(f"Results: {results}")
    
    print("Stopping pool...")
    await pool.stop()
    
    return all(results)


async def main():
    """Run all tests systematically."""
    print("="*80)
    print("SYSTEMATIC TESTING TO IDENTIFY REMAINING ISSUES")
    print("="*80)
    
    # Run tests in order
    await test_with_timeout("Basic Session", test_1_basic_session, 10.0)
    await test_with_timeout("Session with Warmup", test_2_session_with_warmup, 10.0)
    await test_with_timeout("Pool Creation", test_3_pool_creation, 10.0)
    await test_with_timeout("Pool with Warmup", test_4_pool_with_warmup, 15.0)
    await test_with_timeout("Multiple Executions", test_5_multiple_executions, 15.0)
    await test_with_timeout("Concurrent Sessions", test_6_concurrent_sessions, 15.0)
    await test_with_timeout("Pool Concurrent Acquire", test_7_pool_concurrent_acquire, 15.0)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    timeout = sum(1 for r in results if r["status"] == "TIMEOUT")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    
    for result in results:
        status_icon = {
            "PASS": "✓",
            "FAIL": "✗",
            "TIMEOUT": "⏱",
            "ERROR": "💥"
        }.get(result["status"], "?")
        
        print(f"{status_icon} {result['test']:<30} {result['status']:<8} {result['time']:<8}")
        if result["error"]:
            print(f"  └─ {result['error']}")
    
    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {passed}, Failed: {failed}, Timeout: {timeout}, Errors: {errors}")
    
    # Write detailed results to file
    with open("test_results.json", "w") as f:
        import json
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "timeout": timeout,
                "errors": errors
            },
            "results": results
        }, f, indent=2)
    
    print("\nDetailed results saved to test_results.json")


if __name__ == "__main__":
    # Suppress debug logs for cleaner output
    import logging
    import structlog
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    )
    
    asyncio.run(main())