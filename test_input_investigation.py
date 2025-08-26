#!/usr/bin/env python3
"""Investigate input() implementation issues and behavior."""

import asyncio
import sys
import time
import gc
from pathlib import Path
from typing import List, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType


async def test_prompt_flushing():
    """Test if the prompt is flushed to output before input request."""
    print("\n=== Test: Prompt Flushing ===")
    
    session = Session()
    await session.start()
    
    try:
        # Code that uses input with no newline after prompt
        code = """
import sys
sys.stdout.write("Enter name (no newline): ")
sys.stdout.flush()  # Explicit flush
name = input()  # No prompt in input() itself
print(f"Got: {name}")
"""
        
        message = ExecuteMessage(
            id="test-flush",
            timestamp=time.time(),
            code=code,
        )
        
        outputs = []
        inputs = []
        
        async for msg in session.execute(message):
            if msg.type == MessageType.OUTPUT:
                outputs.append(msg.data)
                print(f"OUTPUT: {repr(msg.data)}")
            elif msg.type == MessageType.INPUT:
                inputs.append(msg.prompt)
                print(f"INPUT REQUEST: {repr(msg.prompt)}")
                await session.input_response(msg.id, "TestName")
        
        # Check if prompt appeared in output before input request
        prompt_in_output = any("Enter name" in o for o in outputs)
        print(f"Prompt in output: {prompt_in_output}")
        print(f"Input prompts: {inputs}")
        
        if not prompt_in_output:
            print("❌ ISSUE: Prompt not appearing in output stream")
        else:
            print("✅ Prompt correctly appears in output")
            
    finally:
        await session.shutdown()


async def test_prompt_in_input_function():
    """Test if input('prompt') sends prompt to output."""
    print("\n=== Test: Prompt in input() Function ===")
    
    session = Session()
    await session.start()
    
    try:
        # Simple input with prompt
        code = """
name = input("What is your name? ")
print(f"Hello, {name}!")
"""
        
        message = ExecuteMessage(
            id="test-input-prompt",
            timestamp=time.time(),
            code=code,
        )
        
        outputs = []
        input_prompts = []
        
        async for msg in session.execute(message):
            if msg.type == MessageType.OUTPUT:
                outputs.append(msg.data)
                print(f"OUTPUT: {repr(msg.data)}")
            elif msg.type == MessageType.INPUT:
                input_prompts.append(msg.prompt)
                print(f"INPUT PROMPT: {repr(msg.prompt)}")
                await session.input_response(msg.id, "Alice")
        
        # Check where the prompt appears
        prompt_in_output = any("What is your name?" in o for o in outputs)
        prompt_in_input = any("What is your name?" in p for p in input_prompts)
        
        print(f"Prompt in OUTPUT stream: {prompt_in_output}")
        print(f"Prompt in INPUT message: {prompt_in_input}")
        
        if not prompt_in_output and prompt_in_input:
            print("❌ ISSUE: Prompt only in INPUT message, not flushed to output")
        elif prompt_in_output and prompt_in_input:
            print("⚠️  Prompt appears in both (might be duplicated)")
        elif prompt_in_output and not prompt_in_input:
            print("✅ Prompt correctly flushed to output")
            
    finally:
        await session.shutdown()


async def test_waiter_cleanup():
    """Test if input waiters are properly cleaned up."""
    print("\n=== Test: Waiter Cleanup ===")
    
    session = Session()
    await session.start()
    
    try:
        # Multiple inputs to potentially accumulate waiters
        code = """
import gc
for i in range(5):
    name = input(f"Input {i}: ")
    print(f"Got: {name}")
gc.collect()  # Force garbage collection
"done"
"""
        
        message = ExecuteMessage(
            id="test-waiter-cleanup",
            timestamp=time.time(),
            code=code,
        )
        
        input_count = 0
        async for msg in session.execute(message):
            if msg.type == MessageType.INPUT:
                input_count += 1
                await session.input_response(msg.id, f"Response{input_count}")
                print(f"Responded to input {input_count}")
            elif msg.type == MessageType.RESULT:
                print(f"RESULT: {msg.repr}")
        
        # Now check for leaks by running another execution
        code2 = """
import sys
# Check if we can still do input after previous executions
final = input("Final input: ")
f"Final: {final}"
"""
        
        message2 = ExecuteMessage(
            id="test-cleanup-2",
            timestamp=time.time(),
            code=code2,
        )
        
        async for msg in session.execute(message2):
            if msg.type == MessageType.INPUT:
                await session.input_response(msg.id, "FinalResponse")
                print("✅ Second execution input works - no obvious leak")
            elif msg.type == MessageType.RESULT:
                print(f"Final result: {msg.repr}")
                
    finally:
        await session.shutdown()


async def test_no_response_behavior():
    """Test what happens when we don't send a response."""
    print("\n=== Test: No Response Behavior ===")
    
    session = Session()
    await session.start()
    
    try:
        code = """
import signal
import sys

def timeout_handler(signum, frame):
    raise TimeoutError("Input timed out")

# Set a shorter timeout for testing
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(2)  # 2 second timeout

try:
    name = input("This will timeout: ")
    print(f"Got: {name}")
except TimeoutError as e:
    print(f"Caught timeout: {e}")
    "timeout_handled"
except Exception as e:
    print(f"Other error: {e}")
    "error"
else:
    "success"
finally:
    signal.alarm(0)  # Cancel alarm
"""
        
        message = ExecuteMessage(
            id="test-no-response",
            timestamp=time.time(),
            code=code,
        )
        
        print("Testing no response (will wait for timeout)...")
        
        got_input_request = False
        result = None
        
        async for msg in session.execute(message):
            if msg.type == MessageType.INPUT:
                got_input_request = True
                print(f"INPUT REQUEST: {msg.prompt}")
                print("Not responding to test timeout...")
                # DON'T send response to test timeout
            elif msg.type == MessageType.OUTPUT:
                print(f"OUTPUT: {msg.data}", end="")
            elif msg.type == MessageType.RESULT:
                result = msg.value
                print(f"RESULT: {msg.repr}")
            elif msg.type == MessageType.ERROR:
                print(f"ERROR: {msg.exception_type}: {msg.exception_value}")
        
        if got_input_request:
            print("Got input request as expected")
            if result == "timeout_handled":
                print("✅ Timeout was handled via signal")
            else:
                print(f"❌ Unexpected result: {result}")
                
    finally:
        await session.shutdown()


async def test_shutdown_during_input():
    """Test shutdown while input is waiting."""
    print("\n=== Test: Shutdown During Input ===")
    
    session = Session()
    await session.start()
    
    try:
        code = """
try:
    name = input("Enter name (will shutdown): ")
    print(f"Got: {name}")
    "success"
except EOFError:
    print("Got EOFError on shutdown")
    "eof_error"
except Exception as e:
    print(f"Other error: {type(e).__name__}: {e}")
    "other_error"
"""
        
        message = ExecuteMessage(
            id="test-shutdown",
            timestamp=time.time(),
            code=code,
        )
        
        print("Starting execution...")
        
        # Start execution in background
        exec_task = asyncio.create_task(session.execute(message).__aiter__().__anext__())
        
        # Wait a bit to ensure input is requested
        await asyncio.sleep(0.5)
        
        # Shutdown while waiting for input
        print("Shutting down session while input is waiting...")
        await session.shutdown()
        
        # Check what happened
        try:
            result = await exec_task
            print(f"Got message after shutdown: {result.type}")
        except Exception as e:
            print(f"Exception after shutdown: {type(e).__name__}: {e}")
            
    except Exception as e:
        print(f"Test exception: {e}")


async def test_concurrent_inputs():
    """Test concurrent input requests (should not happen but test behavior)."""
    print("\n=== Test: Concurrent Input Attempts ===")
    
    session = Session()
    await session.start()
    
    try:
        # Try to create a scenario with overlapping inputs
        code = """
import threading
import time

results = []

def get_input1():
    try:
        name = input("Thread 1: ")
        results.append(f"T1: {name}")
    except Exception as e:
        results.append(f"T1 Error: {e}")

def get_input2():
    time.sleep(0.1)  # Small delay
    try:
        name = input("Thread 2: ")
        results.append(f"T2: {name}")
    except Exception as e:
        results.append(f"T2 Error: {e}")

t1 = threading.Thread(target=get_input1)
t2 = threading.Thread(target=get_input2)

t1.start()
t2.start()

t1.join(timeout=5)
t2.join(timeout=5)

print("Results:", results)
results
"""
        
        message = ExecuteMessage(
            id="test-concurrent",
            timestamp=time.time(),
            code=code,
        )
        
        input_count = 0
        responses_sent = []
        
        async for msg in session.execute(message):
            if msg.type == MessageType.INPUT:
                input_count += 1
                response = f"Response{input_count}"
                responses_sent.append(response)
                print(f"INPUT {input_count}: {msg.prompt}")
                await session.input_response(msg.id, response)
            elif msg.type == MessageType.OUTPUT:
                print(f"OUTPUT: {msg.data}", end="")
            elif msg.type == MessageType.RESULT:
                print(f"RESULT: {msg.value}")
                if input_count == 2:
                    print("✅ Both concurrent inputs were handled")
                else:
                    print(f"⚠️  Only {input_count} inputs handled (expected 2)")
                    
    finally:
        await session.shutdown()


async def test_input_token_uniqueness():
    """Test that input tokens are unique and properly managed."""
    print("\n=== Test: Input Token Management ===")
    
    session = Session()
    await session.start()
    
    try:
        code = """
# Rapid sequential inputs
inputs = []
for i in range(3):
    val = input(f"Quick input {i}: ")
    inputs.append(val)
print("All inputs:", inputs)
inputs
"""
        
        message = ExecuteMessage(
            id="test-tokens",
            timestamp=time.time(),
            code=code,
        )
        
        tokens_seen = set()
        responses = ["A", "B", "C"]
        response_idx = 0
        
        async for msg in session.execute(message):
            if msg.type == MessageType.INPUT:
                token = msg.id
                if token in tokens_seen:
                    print(f"❌ DUPLICATE TOKEN: {token}")
                else:
                    tokens_seen.add(token)
                    print(f"Token {response_idx}: {token[:8]}...")
                    
                if response_idx < len(responses):
                    await session.input_response(token, responses[response_idx])
                    response_idx += 1
            elif msg.type == MessageType.RESULT:
                if msg.value == responses:
                    print("✅ All inputs received correct responses")
                else:
                    print(f"❌ Wrong responses: expected {responses}, got {msg.value}")
                    
    finally:
        await session.shutdown()


async def main():
    """Run all input investigation tests."""
    print("=" * 60)
    print("INPUT IMPLEMENTATION INVESTIGATION")
    print("=" * 60)
    
    # Run tests
    await test_prompt_flushing()
    await test_prompt_in_input_function()
    await test_waiter_cleanup()
    await test_no_response_behavior()
    # Skip shutdown test as it's complex
    # await test_shutdown_during_input()
    await test_concurrent_inputs()
    await test_input_token_uniqueness()
    
    print("\n" + "=" * 60)
    print("Investigation complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())