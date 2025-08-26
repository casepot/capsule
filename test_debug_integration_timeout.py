#!/usr/bin/env python3
"""Debug why integration test times out"""

import asyncio
import sys
import time
import uuid
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from src.protocol.messages import ExecuteMessage, MessageType, Message
from src.session.pool import SessionPool  
from src.session.manager import Session


async def test_with_explicit_logging():
    """Test with detailed logging at each step"""
    print("Starting test with explicit logging...")
    
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        session = await pool.acquire()
        print(f"Session acquired, state: {session._state}")
        
        # Create message
        msg = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code='x = 42; print(f"Value: {x}")'
        )
        
        print(f"\nStarting async for loop over session.execute(msg)...")
        print(f"Message ID: {msg.id}")
        
        messages_received = []
        iteration = 0
        
        # Try with timeout on the whole loop
        try:
            async with asyncio.timeout(5.0):
                async for message in session.execute(msg):
                    iteration += 1
                    print(f"  Iteration {iteration}: Received {message.type}")
                    messages_received.append(message)
                    
                    # Check what the comparison looks like
                    is_result = message.type == "result"
                    is_error = message.type == "error"
                    is_terminal_string = message.type in ["result", "error"]
                    is_terminal_enum = message.type in [MessageType.RESULT, MessageType.ERROR]
                    
                    print(f"    Type checks: is_result={is_result}, is_error={is_error}")
                    print(f"    Terminal (string): {is_terminal_string}, Terminal (enum): {is_terminal_enum}")
                    
                    # Let's check what Session.execute is checking
                    print(f"    Line 274 check would be: {message.type} in {[MessageType.RESULT, MessageType.ERROR]}")
                    print(f"    Result: {message.type in [MessageType.RESULT, MessageType.ERROR]}")
                    
                print("ASYNC FOR LOOP COMPLETED NATURALLY")
                
        except asyncio.TimeoutError:
            print(f"TIMEOUT after 5 seconds at iteration {iteration}")
            print(f"Messages received: {[m.type for m in messages_received]}")
        
        print(f"\nFinal session state: {session._state}")
        
    finally:
        await pool.stop()


async def test_session_execute_internals():
    """Look at what's happening inside session.execute()"""
    print("\nTesting session.execute() internals...")
    
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        session = await pool.acquire()
        
        # Monkey-patch to add logging
        original_execute = session.execute
        
        async def logged_execute(message, timeout=30.0):
            print(f"[execute] Called with message type: {message.type}")
            print(f"[execute] Timeout: {timeout}")
            
            async for msg in original_execute(message, timeout):
                print(f"[execute] Yielding message type: {msg.type}")
                
                # Check the termination condition
                should_break = msg.type in [MessageType.RESULT, MessageType.ERROR]
                print(f"[execute] Should break? {should_break} (msg.type={msg.type!r})")
                
                yield msg
                
                if should_break:
                    print("[execute] Breaking from generator")
                    break
        
        session.execute = logged_execute
        
        # Now run a simple execution
        msg = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code='42'
        )
        
        messages = []
        async for message in session.execute(msg):
            messages.append(message.type)
            print(f"Main loop received: {message.type}")
        
        print(f"Total messages: {messages}")
        
    finally:
        await pool.stop()


async def test_check_actual_comparison():
    """Verify the actual line 274 comparison"""
    print("\nChecking actual line 274 comparison...")
    
    # Test with actual values
    test_types = ["result", "error", "output", "ready"]
    
    for test_type in test_types:
        in_enum_list = test_type in [MessageType.RESULT, MessageType.ERROR]
        equals_enum = test_type == MessageType.RESULT or test_type == MessageType.ERROR
        
        print(f"  '{test_type}':")
        print(f"    in [MessageType.RESULT, MessageType.ERROR]: {in_enum_list}")
        print(f"    == MessageType.RESULT or ERROR: {equals_enum}")
    
    # Check what MessageType actually is
    print(f"\nMessageType.RESULT value: {MessageType.RESULT}")
    print(f"MessageType.RESULT type: {type(MessageType.RESULT)}")
    print(f"Is MessageType.RESULT a str? {isinstance(MessageType.RESULT, str)}")
    print(f"'result' == MessageType.RESULT: {'result' == MessageType.RESULT}")


async def main():
    """Run debug tests"""
    import logging
    # Enable some logging
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("DEBUG: Integration Test Timeout")
    print("="*60)
    
    await test_check_actual_comparison()
    await test_with_explicit_logging()
    # await test_session_execute_internals()  # Uncomment if needed


if __name__ == "__main__":
    asyncio.run(main())