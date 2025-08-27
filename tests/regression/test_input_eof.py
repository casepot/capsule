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
    """Demonstrate that basic input() call fails with EOFError."""
    print("\n=== Test: Basic input() fails ===")
    
    session = Session()
    await session.start()
    
    try:
        # This should request input, but will fail with EOFError
        code = """
name = input("What's your name? ")
print(f"Hello, {name}!")
"""
        
        message = ExecuteMessage(
            id="test-input-1",
            timestamp=time.time(),
            code=code,
        )
        
        print(f"Executing code that uses input()...")
        error_found = False
        
        async for msg in session.execute(message):
            if msg.type == MessageType.OUTPUT:
                print(f"OUTPUT: {msg.data}", end="")
            elif msg.type == MessageType.ERROR:
                print(f"ERROR: {msg.exception_type}: {msg.exception_message}")
                if "EOFError" in msg.exception_type:
                    error_found = True
                    print("❌ CONFIRMED: input() causes EOFError")
        
        if not error_found:
            print("⚠️ UNEXPECTED: No EOFError found")
            
    finally:
        await session.shutdown()
    
    return error_found


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


async def main():
    """Run all input handling test reproductions."""
    print("=" * 60)
    print("INPUT HANDLING ISSUE REPRODUCTION")
    print("=" * 60)
    
    # Test 1: Basic input fails
    failed = await test_basic_input_fails()
    
    # Test 2: Multiple inputs fail
    await test_multiple_inputs_fail()
    
    # Test 3: Input in function fails
    await test_input_in_function_fails()
    
    # Test 4: Show InputHandler exists but unused
    await test_input_handler_exists_but_unused()
    
    print("\n" + "=" * 60)
    print("SUMMARY: input() is completely broken")
    print("Root cause: InputHandler exists but never connected to builtin")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())