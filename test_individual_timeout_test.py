#!/usr/bin/env python3
"""Test the exact integration pattern to see if it times out"""

import asyncio
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.protocol.messages import ExecuteMessage
from src.session.pool import SessionPool
from src.session.manager import Session


class ExecutionResult:
    """Helper class to collect execution results - exact copy from integration test"""
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
        
        print(f"Starting async generator for code: {code!r}")
        message_count = 0
        
        async for message in session.execute(msg):
            message_count += 1
            print(f"  Message {message_count}: {message.type}")
            self.messages.append(message)
            if message.type == "output":
                self.output += message.data
            elif message.type == "result":
                self.value = message.value
            elif message.type == "error":
                self.error = message.exception_message
                self.traceback = message.traceback
        
        print(f"Generator completed after {message_count} messages")


async def test_exact_integration_pattern():
    """Test the exact pattern from test_integration_message_types.py"""
    print("Testing exact integration pattern...")
    print("=" * 60)
    
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        session = await pool.acquire()
        print(f"Session acquired: {session.session_id}")
        print(f"Session state: {session._state}")
        
        # Test 1: Simple execution
        print("\n--- Test 1: Simple execution ---")
        result = ExecutionResult()
        
        try:
            async with asyncio.timeout(5.0):
                await result.collect(session, "x = 42; print(f'Value: {x}')")
                print(f"SUCCESS: Execution completed")
                print(f"Output: {result.output!r}")
                print(f"Value: {result.value}")
                print(f"Message types: {[m.type for m in result.messages]}")
        except asyncio.TimeoutError:
            print(f"TIMEOUT after 5 seconds!")
            print(f"Messages before timeout: {[m.type for m in result.messages]}")
            print(f"Output collected: {result.output!r}")
        
        print(f"Session state after: {session._state}")
        
        # Test 2: Multiple executions (if first succeeded)
        if not result.error and result.messages:
            print("\n--- Test 2: Second execution ---")
            result2 = ExecutionResult()
            
            try:
                async with asyncio.timeout(5.0):
                    await result2.collect(session, "x * 2")
                    print(f"SUCCESS: Second execution completed")
                    print(f"Value: {result2.value}")
            except asyncio.TimeoutError:
                print(f"TIMEOUT on second execution!")
        
    finally:
        print("\n--- Cleanup ---")
        await pool.stop()
        print("Pool stopped")


async def test_simple_async_for():
    """Test the simplest possible async for loop"""
    print("\n" + "=" * 60)
    print("Testing simple async for loop...")
    
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        session = await pool.acquire()
        
        msg = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code='42'
        )
        
        print("Starting async for loop...")
        count = 0
        
        async for message in session.execute(msg):
            count += 1
            print(f"Message {count}: {message.type}")
            if count > 10:  # Safety limit
                print("Safety limit reached, breaking")
                break
        
        print(f"Loop completed after {count} messages")
        
    finally:
        await pool.stop()


async def main():
    """Run tests"""
    try:
        await test_exact_integration_pattern()
        await test_simple_async_for()
        print("\n" + "=" * 60)
        print("All tests completed successfully")
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run with logging disabled for clarity
    import logging
    logging.getLogger("structlog").setLevel(logging.ERROR)
    
    asyncio.run(main())