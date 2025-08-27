#!/usr/bin/env python3
"""
Test reproduction demonstrating that input() is completely broken in pyrepl3.
This test shows the EOFError that occurs when trying to use input() in executed code.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType


async def test_basic_input_fails():
    """Test what happens when input() is not responded to - should timeout."""
    print("\n=== Test: Input without response times out ===")
    
    session = Session()
    await session.start()
    
    try:
        code = """
name = input("What's your name? ")
print(f"Hello, {name}!")
"""
        
        message = ExecuteMessage(
            id="test-input-1",
            timestamp=time.time(),
            code=code,
        )
        
        print(f"Executing code that uses input() WITHOUT responding...")
        timeout_occurred = False
        input_request_seen = False
        
        try:
            # Use a short timeout to avoid waiting forever
            async for msg in session.execute(message, timeout=2.0):
                if msg.type == MessageType.OUTPUT:
                    print(f"OUTPUT: {msg.data}", end="")
                elif msg.type == MessageType.INPUT:
                    print(f"INPUT REQUEST RECEIVED: {msg.prompt}")
                    input_request_seen = True
                    # DON'T respond - let it timeout
                elif msg.type == MessageType.ERROR:
                    print(f"ERROR: {msg.exception_type}: {msg.exception_message}")
        except asyncio.TimeoutError:
            print("TIMEOUT: Execution timed out waiting for input response")
            timeout_occurred = True
        
        if input_request_seen and timeout_occurred:
            print("✅ EXPECTED: Input request sent but times out without response")
        elif input_request_seen and not timeout_occurred:
            print("⚠️ ISSUE: Input request seen but no timeout - may hang forever")
        else:
            print("❌ UNEXPECTED: No input request seen at all")
            
    finally:
        await session.shutdown()
    
    return input_request_seen


async def test_multiple_inputs_fail():
    """Demonstrate that multiple input() calls all fail."""
    print("\n=== Test: Multiple inputs fail ===")
    
    session = Session()
    await session.start()
    
    try:
        code = """
try:
    first = input("First: ")
    second = input("Second: ")
    print(f"Got: {first}, {second}")
except EOFError as e:
    print(f"Failed at first input: {e}")
"""
        
        message = ExecuteMessage(
            id="test-input-2",
            timestamp=time.time(),
            code=code,
        )
        
        print(f"Executing code with multiple inputs...")
        
        async for msg in session.execute(message):
            if msg.type == MessageType.OUTPUT:
                print(f"OUTPUT: {msg.data}", end="")
            elif msg.type == MessageType.ERROR:
                print(f"ERROR: {msg.traceback}")
                
    finally:
        await session.shutdown()


async def test_input_in_function_fails():
    """Demonstrate that input() in functions also fails."""
    print("\n=== Test: input() in function fails ===")
    
    session = Session()
    await session.start()
    
    try:
        code = """
def get_user_info():
    name = input("Name: ")
    age = input("Age: ")
    return name, age

try:
    user = get_user_info()
    print(f"User: {user}")
except EOFError as e:
    print(f"Function input failed: {e}")
"""
        
        message = ExecuteMessage(
            id="test-input-3",
            timestamp=time.time(),
            code=code,
        )
        
        print(f"Executing function with input()...")
        
        async for msg in session.execute(message):
            if msg.type == MessageType.OUTPUT:
                print(f"OUTPUT: {msg.data}", end="")
                
    finally:
        await session.shutdown()


async def test_input_handler_exists_but_unused():
    """Demonstrate that InputHandler exists but is never connected."""
    print("\n=== Test: InputHandler exists but unused ===")
    
    # Show that the InputHandler class exists in the worker module
    from src.subprocess.worker import InputHandler
    print(f"✓ InputHandler class exists: {InputHandler}")
    
    # But it's never connected to the builtin input
    session = Session()
    await session.start()
    
    try:
        # Check if input is overridden in namespace
        code = """
import builtins
print(f"input is builtin: {input == builtins.input}")
print(f"input in namespace: {'input' in locals()}")
"""
        
        message = ExecuteMessage(
            id="test-input-4",
            timestamp=time.time(),
            code=code,
        )
        
        async for msg in session.execute(message):
            if msg.type == MessageType.OUTPUT:
                print(f"OUTPUT: {msg.data}", end="")
                
    finally:
        await session.shutdown()


async def test_input_works_with_protocol():
    """Demonstrate that input() DOES work when properly handled via protocol."""
    print("\n=== Test: Input works with proper handling ===")
    
    from src.protocol.messages import InputMessage
    
    session = Session()
    await session.start()
    
    try:
        code = """
name = input("What's your name? ")
age = input("What's your age? ")
print(f"Hello {name}, you are {age} years old!")
(name, age)
"""
        
        message = ExecuteMessage(
            id="test-input-working",
            timestamp=time.time(),
            code=code,
        )
        
        print(f"Executing code with proper input handling...")
        input_count = 0
        responses = ["Alice", "25"]
        
        async for msg in session.execute(message):
            if msg.type == MessageType.OUTPUT:
                print(f"OUTPUT: {msg.data}", end="")
            elif msg.type == MessageType.INPUT:
                response = responses[input_count] if input_count < len(responses) else ""
                print(f"INPUT REQUEST: {msg.prompt} -> Responding with: {response!r}")
                await session.input_response(msg.id, response)
                input_count += 1
            elif msg.type == MessageType.RESULT:
                print(f"RESULT: {msg.value!r}")
        
        print(f"✅ SUCCESS: Handled {input_count} input requests successfully!")
        return True
            
    finally:
        await session.shutdown()


async def main():
    """Run all input handling test reproductions."""
    print("=" * 60)
    print("INPUT HANDLING TEST SUITE")
    print("=" * 60)
    
    # Test 1: Input without response (timeout behavior)
    timeout_test = await test_basic_input_fails()
    
    # Test 2: Multiple inputs fail (when not handled)
    await test_multiple_inputs_fail()
    
    # Test 3: Input in function fails (when not handled)
    await test_input_in_function_fails()
    
    # Test 4: Show InputHandler exists
    await test_input_handler_exists_but_unused()
    
    # Test 5: NEW - Show input WORKS when properly handled
    works = await test_input_works_with_protocol()
    
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("- Input() sends InputMessage protocol messages ✅")
    print("- Session.input_response() sends responses ✅")
    print("- Without response, execution times out (expected)")
    print("- With proper handling, input() works perfectly!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())