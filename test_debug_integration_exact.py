#!/usr/bin/env python3
"""Debug exact integration test pattern with detailed tracing"""

import asyncio
import sys
import time
import uuid
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from src.session.pool import SessionPool
from src.session.manager import Session
from src.protocol.messages import (
    ExecuteMessage, 
    OutputMessage,
    ResultMessage,
    ErrorMessage,
    Message
)


class ExecutionResult:
    """Helper class to collect execution results - EXACT COPY from integration"""
    def __init__(self):
        self.output = ""
        self.error: Optional[str] = None
        self.traceback: Optional[str] = None
        self.value = None
        self.messages: List[Message] = []
    
    async def collect(self, session: Session, code: str):
        """Collect all messages from execution."""
        print(f"\n[collect] Starting for code: {code!r}")
        msg = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code=code
        )
        
        print(f"[collect] Created ExecuteMessage id={msg.id}")
        print(f"[collect] Entering async for loop...")
        
        message_count = 0
        start_time = time.time()
        
        async for message in session.execute(msg):
            message_count += 1
            elapsed = time.time() - start_time
            print(f"[collect] Message {message_count} at {elapsed:.3f}s: type={message.type!r}")
            
            self.messages.append(message)
            if message.type == "output":
                print(f"[collect]   Output data: {message.data!r}")
                self.output += message.data
            elif message.type == "result":
                print(f"[collect]   Result value: {message.value!r}")
                self.value = message.value
            elif message.type == "error":
                print(f"[collect]   Error: {message.exception_message!r}")
                self.error = message.exception_message
                self.traceback = message.traceback
            
            # Check if this should be terminal
            is_terminal = message.type in ["result", "error"]
            print(f"[collect]   Is terminal? {is_terminal}")
        
        print(f"[collect] Async for loop COMPLETED after {message_count} messages")


async def test_exact_integration_pattern():
    """Test exact pattern from test_integration_message_types.py line 54"""
    print("="*60)
    print("Testing EXACT integration pattern")
    print("="*60)
    
    pool = SessionPool(max_sessions=1)
    print("Created pool")
    await pool.start()
    print("Pool started")
    
    try:
        # Get session - EXACT pattern from line 62
        session = await pool.acquire()
        print(f"Session acquired: {session.session_id}")
        print(f"Session state: {session._state}")
        
        # Test execute - EXACT pattern from line 65
        print("\n--- Testing execute message (line 65) ---")
        result = ExecutionResult()
        
        # Add timeout to see where it hangs
        try:
            async with asyncio.timeout(10.0):
                await result.collect(session, "x = 42; print(f'Value: {x}')")
                print("✓ collect() completed successfully")
        except asyncio.TimeoutError:
            print("✗ TIMEOUT in collect()")
            print(f"Messages received: {[m.type for m in result.messages]}")
            print(f"Output so far: {result.output!r}")
            return
        
        # Assertions from line 68-70
        assert result.output == "Value: 42\n"
        assert result.error is None
        print("✓ Execute message works")
        
        # Test multiple executions - EXACT pattern from line 73
        print("\n--- Testing multiple executions (line 73) ---")
        result = ExecutionResult()
        
        try:
            async with asyncio.timeout(10.0):
                await result.collect(session, "x * 2")
                print("✓ Second collect() completed")
        except asyncio.TimeoutError:
            print("✗ TIMEOUT in second collect()")
            print(f"Messages: {[m.type for m in result.messages]}")
            return
        
        assert result.value == 84
        print("✓ Multiple executions work")
        
    finally:
        await pool.stop()
        print("\nPool stopped successfully")


async def test_minimal_collect():
    """Test just the collect pattern in isolation"""
    print("\n" + "="*60)
    print("Testing minimal collect pattern")
    print("="*60)
    
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        session = await pool.acquire()
        
        # Directly test the async for pattern
        msg = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code='42'
        )
        
        print("Testing async for with manual collection...")
        messages = []
        count = 0
        
        async for message in session.execute(msg):
            count += 1
            print(f"  Message {count}: {message.type}")
            messages.append(message)
            
            # Manual check like ExecutionResult does
            if message.type == "output":
                pass  # Just collect
            elif message.type == "result":
                pass  # Just collect  
            elif message.type == "error":
                pass  # Just collect
        
        print(f"Loop completed with {count} messages")
        print(f"Message types: {[m.type for m in messages]}")
        
    finally:
        await pool.stop()


async def main():
    """Run debug tests"""
    import logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise
    
    try:
        await test_minimal_collect()
        await test_exact_integration_pattern()
        print("\n" + "="*60)
        print("✅ All tests completed")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())