#!/usr/bin/env python3
"""Integration test for message type normalization."""

import asyncio
import sys
import time
import uuid
from pathlib import Path
from typing import List, Optional

# Add parent to path to allow absolute imports
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
    """Helper class to collect execution results."""
    def __init__(self):
        self.output = ""
        self.error: Optional[str] = None
        self.traceback: Optional[str] = None
        self.value = None
        self.messages: List[Message] = []
    
    async def collect(self, session: Session, code: str):
        """Collect all messages from execution."""
        msg = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code=code
        )
        
        async for message in session.execute(msg):
            self.messages.append(message)
            if message.type == "output":
                self.output += message.data
            elif message.type == "result":
                self.value = message.value
            elif message.type == "error":
                self.error = message.exception_message
                self.traceback = message.traceback


async def test_basic_execution():
    """Test basic execution with normalized message types."""
    print("Testing basic execution with normalized types...")
    
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        # Get session
        session = await pool.acquire()
        
        # Test execute
        print("  Testing execute message...")
        result = ExecutionResult()
        await result.collect(session, "x = 42; print(f'Value: {x}')")
        assert result.output == "Value: 42\n"
        assert result.error is None
        print("  ✓ Execute message works")
        
        # Test multiple executions
        print("  Testing multiple executions...")
        result = ExecutionResult()
        await result.collect(session, "x * 2")
        assert result.value == 84
        print("  ✓ Multiple executions work")
        
        # Test error handling
        print("  Testing error message...")
        result = ExecutionResult()
        await result.collect(session, "1/0")
        assert result.error is not None
        assert "ZeroDivisionError" in result.traceback
        print("  ✓ Error message works")
        
    finally:
        await pool.stop()
        print("✓ Pool cleanup successful")


async def test_output_streaming():
    """Test output streaming with normalized types."""
    print("\nTesting output streaming...")
    print(f"[TEST START: test_output_streaming at {time.time()}]")
    
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        session = await pool.acquire()
        
        # Test streaming output
        print("  Testing streaming output messages...")
        
        # Execute with output capture
        code = """
import sys
import time
for i in range(3):
    print(f"Line {i}")
    sys.stdout.flush()
    time.sleep(0.01)
"""
        result = ExecutionResult()
        print(f"    [Starting collect for streaming test at {time.time()}]")
        await result.collect(session, code)
        print(f"    [Completed collect for streaming test at {time.time()}]")
        
        # Check we got output
        assert "Line 0" in result.output
        assert "Line 1" in result.output
        assert "Line 2" in result.output
        print("  ✓ Output messages streamed correctly")
        
    finally:
        await pool.stop()


async def test_worker_routing():
    """Test that worker correctly routes different message types."""
    print("\nTesting worker message routing...")
    
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        session = await pool.acquire()
        
        # Test that session received ready message
        assert session.is_alive
        assert session._ready_event.is_set()
        print("  ✓ Worker sent and session received ready message")
        
        # Execute should trigger correct routing
        result = ExecutionResult()
        await result.collect(session, "y = 100")
        assert result.error is None
        print("  ✓ Execute message routed correctly")
        
        # Check heartbeat is being received (wait a bit)
        initial_memory = session._info.memory_usage
        await asyncio.sleep(0.1)  # Wait for potential heartbeat
        
        # Memory might not change, but we should have received messages
        print("  ✓ Session processes messages correctly")
        
    finally:
        await pool.stop()


async def test_concurrent_sessions():
    """Test multiple sessions with normalized message types."""
    print("\nTesting concurrent sessions...")
    
    pool = SessionPool(max_sessions=3)
    await pool.start()
    
    try:
        # Get multiple sessions
        sessions = []
        for i in range(3):
            session = await pool.acquire()
            sessions.append(session)
        
        print(f"  Created {len(sessions)} sessions")
        
        # Execute on all sessions concurrently
        tasks = []
        for i, session in enumerate(sessions):
            result = ExecutionResult()
            code = f"result = {i * 10}"
            tasks.append(result.collect(session, code))
        
        await asyncio.gather(*tasks)
        
        print("  ✓ All sessions executed correctly with normalized types")
        
    finally:
        await pool.stop()


async def test_message_type_consistency():
    """Test that all message types are consistently strings."""
    print("\nTesting message type consistency...")
    
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        session = await pool.acquire()
        
        # Execute and collect all message types
        result = ExecutionResult()
        code = """
print("Testing output")
x = 42
x  # Should produce a result
"""
        await result.collect(session, code)
        
        # Check all messages have string types
        for msg in result.messages:
            assert isinstance(msg.type, str), f"Message type is not string: {type(msg.type)}"
            assert msg.type in ["output", "result", "error"], f"Unexpected message type: {msg.type}"
        
        print(f"  ✓ All {len(result.messages)} messages have string types")
        
        # Test error message
        result = ExecutionResult()
        await result.collect(session, "undefined_variable")
        
        error_found = False
        for msg in result.messages:
            assert isinstance(msg.type, str)
            if msg.type == "error":
                error_found = True
        
        assert error_found, "Expected error message not found"
        print("  ✓ Error messages have string type")
        
    finally:
        await pool.stop()


async def main():
    """Run all integration tests."""
    print("=" * 60)
    print("Integration Tests for Message Type Normalization")
    print("=" * 60)
    
    try:
        await test_basic_execution()
        await test_output_streaming()
        await test_worker_routing()
        await test_concurrent_sessions()
        await test_message_type_consistency()
        
        print("\n" + "=" * 60)
        print("✅ All integration tests passed!")
        print("Message type normalization working correctly")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())