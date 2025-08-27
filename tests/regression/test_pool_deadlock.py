#!/usr/bin/env python3
"""
Test reproduction demonstrating the pool blocking issue in pyrepl3.
The third task in asyncio.gather() never completes, causing timeout.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session.pool import SessionPool, PoolConfig
from src.protocol.messages import ExecuteMessage, MessageType


async def test_pool_concurrent_tasks_block():
    """Demonstrate that 3rd concurrent task blocks indefinitely."""
    print("\n=== Test: Pool concurrent tasks block ===")
    
    # Create pool with capacity for all tasks
    config = PoolConfig(
        min_idle=2,
        max_sessions=5,
        warmup_code="x = 1",  # Simple warmup
        pre_warm_on_start=True
    )
    
    pool = SessionPool(config)
    await pool.start()
    
    print(f"Pool started with min_idle={config.min_idle}, max={config.max_sessions}")
    
    async def execute_task(task_id: int):
        """Execute a simple task in a pool session."""
        print(f"[Task {task_id}] Starting acquisition...")
        start_time = time.time()
        
        try:
            # This is where task 2 (third task) blocks
            session = await asyncio.wait_for(pool.acquire(), timeout=5.0)
            acquire_time = time.time() - start_time
            print(f"[Task {task_id}] Acquired session in {acquire_time:.2f}s")
            
            # Execute simple code
            code = f"print('[Task {task_id}] Running'); result = {task_id}; result"
            message = ExecuteMessage(
                id=f"task-{task_id}",
                timestamp=time.time(),
                code=code
            )
            
            result = None
            async for msg in session.execute(message):
                if msg.type == MessageType.OUTPUT:
                    print(f"[Task {task_id}] Output: {msg.data.strip()}")
                elif msg.type == MessageType.RESULT:
                    result = msg.repr
            
            print(f"[Task {task_id}] Releasing session...")
            await pool.release(session)
            print(f"[Task {task_id}] Released successfully")
            
            return result
            
        except asyncio.TimeoutError:
            print(f"[Task {task_id}] ❌ TIMEOUT during acquisition!")
            return None
    
    # Try to run 3 concurrent tasks
    print("\nStarting 3 concurrent tasks...")
    
    try:
        # This will timeout because task 2 blocks
        results = await asyncio.wait_for(
            asyncio.gather(
                execute_task(0),
                execute_task(1),
                execute_task(2),  # This one blocks!
                return_exceptions=True
            ),
            timeout=15.0
        )
        
        print(f"\nAll tasks completed: {results}")
        
    except asyncio.TimeoutError:
        print("\n❌ CONFIRMED: asyncio.gather() timed out!")
        print("Tasks 0 and 1 completed, but Task 2 blocked indefinitely")
    
    await pool.stop()


async def test_pool_sequential_works():
    """Show that sequential task execution works fine."""
    print("\n=== Test: Sequential execution works ===")
    
    config = PoolConfig(
        min_idle=1,
        max_sessions=2,
        warmup_code="x = 1"
    )
    
    pool = SessionPool(config)
    await pool.start()
    
    # Sequential execution works fine
    for i in range(3):
        print(f"\n[Sequential {i}] Acquiring...")
        session = await pool.acquire()
        print(f"[Sequential {i}] Acquired")
        
        code = f"print('Task {i}'); {i}"
        message = ExecuteMessage(
            id=f"seq-{i}",
            timestamp=time.time(),
            code=code
        )
        
        async for msg in session.execute(message):
            if msg.type == MessageType.OUTPUT:
                print(f"[Sequential {i}] Output: {msg.data.strip()}")
        
        await pool.release(session)
        print(f"[Sequential {i}] Released")
    
    print("\n✓ Sequential execution works perfectly")
    
    await pool.stop()


async def test_pool_warmup_deadlock_fixed():
    """Verify that warmup deadlock was actually fixed."""
    print("\n=== Test: Warmup deadlock (should be fixed) ===")
    
    config = PoolConfig(
        min_idle=2,
        max_sessions=3,
        warmup_code="import math; x = math.pi",
        pre_warm_on_start=True
    )
    
    print("Creating pool with warmup code...")
    pool = SessionPool(config)
    
    try:
        # This should complete quickly if warmup deadlock is fixed
        await asyncio.wait_for(pool.start(), timeout=5.0)
        print("✓ Pool started successfully with warmup")
        
    except asyncio.TimeoutError:
        print("❌ Pool start timed out - warmup deadlock still present!")
    
    await pool.stop()


async def test_pool_resource_starvation():
    """Test if the issue is resource starvation."""
    print("\n=== Test: Resource starvation check ===")
    
    config = PoolConfig(
        min_idle=2,
        max_sessions=2,  # Only 2 sessions available
        pre_warm_on_start=False  # Don't pre-warm
    )
    
    pool = SessionPool(config)
    await pool.start()
    
    print(f"Pool has max_sessions={config.max_sessions}")
    
    # Try to acquire 3 sessions when only 2 exist
    sessions = []
    
    for i in range(3):
        print(f"\nTrying to acquire session {i}...")
        try:
            session = await asyncio.wait_for(pool.acquire(), timeout=2.0)
            sessions.append(session)
            print(f"✓ Acquired session {i}")
        except asyncio.TimeoutError:
            print(f"❌ Session {i} acquisition timed out (expected for i=2)")
    
    # Release sessions
    for i, session in enumerate(sessions):
        await pool.release(session)
        print(f"Released session {i}")
    
    await pool.stop()


async def main():
    """Run all pool blocking test reproductions."""
    print("=" * 60)
    print("POOL BLOCKING ISSUE REPRODUCTION")
    print("=" * 60)
    
    # Test 1: Main issue - concurrent tasks block
    await test_pool_concurrent_tasks_block()
    
    # Test 2: Sequential works fine  
    await test_pool_sequential_works()
    
    # Test 3: Verify warmup fix
    await test_pool_warmup_deadlock_fixed()
    
    # Test 4: Check for resource starvation
    await test_pool_resource_starvation()
    
    print("\n" + "=" * 60)
    print("SUMMARY: Third concurrent task blocks in pool.acquire()")
    print("Likely cause: ensure_min_sessions() or acquire/release deadlock")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())