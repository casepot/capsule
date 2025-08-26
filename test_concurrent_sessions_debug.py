#!/usr/bin/env python3
"""Debug concurrent sessions hang issue"""

import asyncio
import sys
import time
import uuid
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

from src.session.pool import SessionPool
from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, Message


class ExecutionResult:
    """Helper class to collect execution results."""
    def __init__(self):
        self.output = ""
        self.error = None
        self.traceback = None
        self.value = None
        self.messages = []
    
    async def collect(self, session: Session, code: str):
        """Collect all messages from execution."""
        msg = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code=code
        )
        
        print(f"    [collect] Session {session.session_id[:8]} executing: {code!r}")
        
        async for message in session.execute(msg):
            self.messages.append(message)
            if message.type == "output":
                self.output += message.data
            elif message.type == "result":
                self.value = message.value
            elif message.type == "error":
                self.error = message.exception_message
                self.traceback = message.traceback
        
        print(f"    [collect] Session {session.session_id[:8]} completed with {len(self.messages)} messages")


async def test_single_session():
    """Test a single session works"""
    print("\n1. Testing single session...")
    
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        session = await pool.acquire()
        print(f"   Acquired session: {session.session_id[:8]}")
        
        result = ExecutionResult()
        await result.collect(session, "result = 42")
        
        print(f"   ✓ Single session works, value={result.value}")
        
    finally:
        await pool.stop()


async def test_two_sessions_sequential():
    """Test two sessions sequentially"""
    print("\n2. Testing two sessions sequentially...")
    
    pool = SessionPool(max_sessions=2)
    await pool.start()
    
    try:
        # First session
        session1 = await pool.acquire()
        print(f"   Acquired session 1: {session1.session_id[:8]}")
        
        result1 = ExecutionResult()
        await result1.collect(session1, "result = 10")
        print(f"   Session 1 result: {result1.value}")
        
        # Second session
        session2 = await pool.acquire()
        print(f"   Acquired session 2: {session2.session_id[:8]}")
        
        result2 = ExecutionResult()
        await result2.collect(session2, "result = 20")
        print(f"   Session 2 result: {result2.value}")
        
        print(f"   ✓ Sequential sessions work")
        
    finally:
        await pool.stop()


async def test_two_sessions_concurrent():
    """Test two sessions concurrently"""
    print("\n3. Testing two sessions concurrently...")
    
    pool = SessionPool(max_sessions=2)
    await pool.start()
    
    try:
        # Get both sessions
        session1 = await pool.acquire()
        print(f"   Acquired session 1: {session1.session_id[:8]}")
        
        session2 = await pool.acquire()
        print(f"   Acquired session 2: {session2.session_id[:8]}")
        
        # Execute on both concurrently
        result1 = ExecutionResult()
        result2 = ExecutionResult()
        
        print("   Starting concurrent executions...")
        tasks = [
            result1.collect(session1, "result = 10"),
            result2.collect(session2, "result = 20")
        ]
        
        await asyncio.gather(*tasks)
        
        print(f"   Session 1 result: {result1.value}")
        print(f"   Session 2 result: {result2.value}")
        print(f"   ✓ Two concurrent sessions work")
        
    finally:
        await pool.stop()


async def test_three_sessions_concurrent():
    """Test three sessions concurrently (the problematic case)"""
    print("\n4. Testing three sessions concurrently...")
    
    pool = SessionPool(max_sessions=3)
    await pool.start()
    
    try:
        # Get all three sessions
        sessions = []
        for i in range(3):
            print(f"   Acquiring session {i+1}...")
            session = await asyncio.wait_for(pool.acquire(), timeout=5.0)
            sessions.append(session)
            print(f"   Acquired session {i+1}: {session.session_id[:8]}")
        
        print(f"   All {len(sessions)} sessions acquired")
        
        # Execute on all sessions concurrently
        tasks = []
        results = []
        for i, session in enumerate(sessions):
            result = ExecutionResult()
            results.append(result)
            code = f"result = {i * 10}"
            print(f"   Preparing task {i}: {code}")
            tasks.append(result.collect(session, code))
        
        print(f"   Starting {len(tasks)} concurrent executions...")
        
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=10.0)
            print("   ✓ All executions completed")
        except asyncio.TimeoutError:
            print("   ✗ TIMEOUT during concurrent execution!")
            for i, result in enumerate(results):
                print(f"     Session {i}: {len(result.messages)} messages received")
        
        for i, result in enumerate(results):
            print(f"   Session {i} result: {result.value}")
        
    except asyncio.TimeoutError:
        print("   ✗ TIMEOUT acquiring sessions!")
    finally:
        await pool.stop()


async def test_three_sessions_with_delays():
    """Test three sessions with delays between acquisitions"""
    print("\n5. Testing three sessions with delays...")
    
    pool = SessionPool(max_sessions=3)
    await pool.start()
    
    try:
        sessions = []
        
        # Acquire with small delays
        for i in range(3):
            print(f"   Acquiring session {i+1}...")
            session = await pool.acquire()
            sessions.append(session)
            print(f"   Acquired session {i+1}: {session.session_id[:8]}")
            await asyncio.sleep(0.1)  # Small delay
        
        # Execute sequentially
        for i, session in enumerate(sessions):
            result = ExecutionResult()
            code = f"result = {i * 10}"
            print(f"   Executing on session {i}: {code}")
            await result.collect(session, code)
            print(f"   Session {i} result: {result.value}")
        
        print("   ✓ Three sessions with delays work")
        
    finally:
        await pool.stop()


async def main():
    """Run debug tests"""
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    print("="*60)
    print("Concurrent Sessions Debug Tests")
    print("="*60)
    
    try:
        await test_single_session()
        await test_two_sessions_sequential()
        await test_two_sessions_concurrent()
        await test_three_sessions_concurrent()
        await test_three_sessions_with_delays()
        
        print("\n" + "="*60)
        print("Debug tests completed")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())