#!/usr/bin/env python3
"""Test the threaded execution model with input() support."""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType


async def test_basic_input():
    """Test that basic input() now works."""
    print("\n=== Test: Basic input() with threading ===")
    
    session = Session()
    await session.start()
    
    try:
        # Code that uses input
        code = """
name = input("What's your name? ")
print(f"Hello, {name}!")
name  # Return the value
"""
        
        message = ExecuteMessage(
            id="test-threaded-input",
            timestamp=time.time(),
            code=code,
        )
        
        print("Executing code that uses input()...")
        
        # Start execution in background
        async def execute_and_collect():
            messages = []
            async for msg in session.execute(message):
                messages.append(msg)
                print(f"Received: {msg.type}")
                
                if msg.type == MessageType.INPUT:
                    print(f"INPUT REQUEST: {msg.prompt}")
                    # Send response using proper API
                    print(f"Sending response: Alice")
                    await session.input_response(msg.id, "Alice")
                    
                elif msg.type == MessageType.OUTPUT:
                    print(f"OUTPUT: {msg.data}", end="")
                    
                elif msg.type == MessageType.RESULT:
                    print(f"RESULT: {msg.repr}")
                    
            return messages
            
        messages = await execute_and_collect()
        
        # Check results
        input_found = any(m.type == MessageType.INPUT for m in messages)
        output_found = any(m.type == MessageType.OUTPUT and "Hello, Alice!" in m.data for m in messages)
        result_found = any(m.type == MessageType.RESULT for m in messages)
        
        if input_found and output_found and result_found:
            print("✅ SUCCESS: input() works with threading!")
        else:
            print(f"❌ FAILED: input={input_found}, output={output_found}, result={result_found}")
            
    finally:
        await session.shutdown()


async def test_multiple_inputs():
    """Test multiple sequential inputs."""
    print("\n=== Test: Multiple inputs ===")
    
    session = Session()
    await session.start()
    
    try:
        code = """
first = input("First name: ")
last = input("Last name: ")
age = input("Age: ")
print(f"{first} {last} is {age} years old")
f"{first} {last}"  # Return value
"""
        
        message = ExecuteMessage(
            id="test-multi-input",
            timestamp=time.time(),
            code=code,
        )
        
        print("Executing code with multiple inputs...")
        
        input_prompts = []
        responses = ["John", "Doe", "30"]
        response_index = 0
        
        async for msg in session.execute(message):
            if msg.type == MessageType.INPUT:
                print(f"INPUT REQUEST: {msg.prompt}")
                input_prompts.append(msg.prompt)
                
                # Send appropriate response
                if response_index < len(responses):
                    await session.input_response(msg.id, responses[response_index])
                    response_index += 1
                    
            elif msg.type == MessageType.OUTPUT:
                print(f"OUTPUT: {msg.data}", end="")
                
            elif msg.type == MessageType.RESULT:
                print(f"RESULT: {msg.repr}")
                
        if len(input_prompts) == 3 and response_index == 3:
            print("✅ SUCCESS: Multiple inputs work!")
        else:
            print(f"❌ FAILED: Got {len(input_prompts)} prompts, sent {response_index} responses")
            
    finally:
        await session.shutdown()


async def test_input_in_function():
    """Test input() inside a function."""
    print("\n=== Test: input() in function ===")
    
    session = Session()
    await session.start()
    
    try:
        code = """
def get_user_info():
    name = input("Enter your name: ")
    age = input("Enter your age: ")
    return f"{name} ({age} years)"

result = get_user_info()
print(f"User info: {result}")
result
"""
        
        message = ExecuteMessage(
            id="test-func-input",
            timestamp=time.time(),
            code=code,
        )
        
        responses = ["Bob", "25"]
        response_index = 0
        
        async for msg in session.execute(message):
            if msg.type == MessageType.INPUT:
                print(f"INPUT REQUEST: {msg.prompt}")
                
                if response_index < len(responses):
                    await session.input_response(msg.id, responses[response_index])
                    response_index += 1
                    
            elif msg.type == MessageType.OUTPUT:
                print(f"OUTPUT: {msg.data}", end="")
                if "Bob (25 years)" in msg.data:
                    print("✅ SUCCESS: input() in function works!")
                    
    finally:
        await session.shutdown()


async def test_input_with_timeout():
    """Test that input timeout is handled."""
    print("\n=== Test: input() timeout handling ===")
    
    session = Session()
    await session.start()
    
    try:
        # Modify timeout for testing
        code = """
try:
    # This will timeout since we won't send a response
    name = input("This will timeout: ")
except TimeoutError as e:
    print(f"Caught timeout: {e}")
    "timeout_handled"
"""
        
        message = ExecuteMessage(
            id="test-timeout",
            timestamp=time.time(),
            code=code,
        )
        
        print("Testing timeout handling (this will take a moment)...")
        
        # Don't send any response to trigger timeout
        async for msg in session.execute(message):
            if msg.type == MessageType.INPUT:
                print(f"INPUT REQUEST: {msg.prompt}")
                # Deliberately don't respond
                print("Not responding to trigger timeout...")
                
            elif msg.type == MessageType.OUTPUT:
                print(f"OUTPUT: {msg.data}", end="")
                
            elif msg.type == MessageType.ERROR:
                if "TimeoutError" in msg.exception_type:
                    print("✅ Timeout detected as expected")
                    
    finally:
        await session.shutdown()


async def main():
    """Run all threaded input tests."""
    print("=" * 60)
    print("THREADED INPUT TESTING")
    print("=" * 60)
    
    await test_basic_input()
    await test_multiple_inputs()
    await test_input_in_function()
    # await test_input_with_timeout()  # Skip timeout test for now
    
    print("\n" + "=" * 60)
    print("Testing complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())