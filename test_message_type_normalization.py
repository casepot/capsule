#!/usr/bin/env python3
"""Test message type normalization to ensure consistency."""

import asyncio
import sys
import uuid
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from protocol.messages import (
    parse_message,
    ExecuteMessage,
    OutputMessage,
    InputMessage,
    InputResponseMessage,
    ResultMessage,
    ErrorMessage,
    ReadyMessage,
    HeartbeatMessage,
    CheckpointMessage,
    RestoreMessage,
    ShutdownMessage,
    MessageType,
)


def test_parse_message_with_string_types():
    """Test that parse_message works with string type values."""
    print("Testing parse_message with string types...")
    
    # Test execute message
    data = {
        "type": "execute",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "code": "print('hello')",
    }
    msg = parse_message(data)
    assert msg.type == "execute"
    assert isinstance(msg, ExecuteMessage)
    print("  ✓ Execute message parsed correctly")
    
    # Test output message
    data = {
        "type": "output",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "data": "hello",
        "stream": "stdout",
        "execution_id": str(uuid.uuid4()),
    }
    msg = parse_message(data)
    assert msg.type == "output"
    assert isinstance(msg, OutputMessage)
    print("  ✓ Output message parsed correctly")
    
    # Test input message
    data = {
        "type": "input",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "prompt": "Enter value: ",
        "execution_id": str(uuid.uuid4()),
    }
    msg = parse_message(data)
    assert msg.type == "input"
    assert isinstance(msg, InputMessage)
    print("  ✓ Input message parsed correctly")
    
    # Test input response message
    data = {
        "type": "input_response",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "data": "user input",
        "input_id": str(uuid.uuid4()),
    }
    msg = parse_message(data)
    assert msg.type == "input_response"
    assert isinstance(msg, InputResponseMessage)
    print("  ✓ Input response message parsed correctly")
    
    # Test result message
    data = {
        "type": "result",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "value": 42,
        "repr": "42",
        "execution_id": str(uuid.uuid4()),
        "execution_time": 0.1,
    }
    msg = parse_message(data)
    assert msg.type == "result"
    assert isinstance(msg, ResultMessage)
    print("  ✓ Result message parsed correctly")
    
    # Test error message
    data = {
        "type": "error",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "traceback": "Traceback...",
        "exception_type": "ValueError",
        "exception_message": "Invalid value",
    }
    msg = parse_message(data)
    assert msg.type == "error"
    assert isinstance(msg, ErrorMessage)
    print("  ✓ Error message parsed correctly")
    
    # Test ready message
    data = {
        "type": "ready",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "session_id": str(uuid.uuid4()),
        "capabilities": ["execute", "input"],
    }
    msg = parse_message(data)
    assert msg.type == "ready"
    assert isinstance(msg, ReadyMessage)
    print("  ✓ Ready message parsed correctly")
    
    # Test heartbeat message
    data = {
        "type": "heartbeat",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "memory_usage": 1000000,
        "cpu_percent": 10.5,
        "namespace_size": 10,
    }
    msg = parse_message(data)
    assert msg.type == "heartbeat"
    assert isinstance(msg, HeartbeatMessage)
    print("  ✓ Heartbeat message parsed correctly")
    
    # Test checkpoint message
    data = {
        "type": "checkpoint",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "data": b"checkpoint_data",
        "namespace_size": 10,
        "function_count": 5,
        "class_count": 2,
        "checkpoint_size": 100,
    }
    msg = parse_message(data)
    assert msg.type == "checkpoint"
    assert isinstance(msg, CheckpointMessage)
    print("  ✓ Checkpoint message parsed correctly")
    
    # Test restore message
    data = {
        "type": "restore",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "data": b"restore_data",
    }
    msg = parse_message(data)
    assert msg.type == "restore"
    assert isinstance(msg, RestoreMessage)
    print("  ✓ Restore message parsed correctly")
    
    # Test shutdown message
    data = {
        "type": "shutdown",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "reason": "Test shutdown",
    }
    msg = parse_message(data)
    assert msg.type == "shutdown"
    assert isinstance(msg, ShutdownMessage)
    print("  ✓ Shutdown message parsed correctly")


def test_message_creation_types():
    """Test that created messages have string types."""
    print("\nTesting message creation types...")
    
    # Create execute message
    msg = ExecuteMessage(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        code="print('hello')",
    )
    assert msg.type == "execute"
    assert isinstance(msg.type, str)
    print("  ✓ ExecuteMessage has string type")
    
    # Create output message
    msg = OutputMessage(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        data="hello",
        stream="stdout",
        execution_id=str(uuid.uuid4()),
    )
    assert msg.type == "output"
    assert isinstance(msg.type, str)
    print("  ✓ OutputMessage has string type")
    
    # Create ready message
    msg = ReadyMessage(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        session_id=str(uuid.uuid4()),
        capabilities=["execute"],
    )
    assert msg.type == "ready"
    assert isinstance(msg.type, str)
    print("  ✓ ReadyMessage has string type")
    
    # Create error message
    msg = ErrorMessage(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        traceback="Traceback...",
        exception_type="ValueError",
        exception_message="Invalid value",
    )
    assert msg.type == "error"
    assert isinstance(msg.type, str)
    print("  ✓ ErrorMessage has string type")


def test_serialization_consistency():
    """Test that message types remain strings through serialization."""
    print("\nTesting serialization consistency...")
    
    # Create a message
    msg = ExecuteMessage(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        code="x = 42",
    )
    
    # Serialize to dict (as would happen in transport)
    data = msg.model_dump(mode="json")
    assert data["type"] == "execute"
    assert isinstance(data["type"], str)
    print("  ✓ Serialized type is string")
    
    # Parse back
    parsed = parse_message(data)
    assert parsed.type == "execute"
    assert isinstance(parsed.type, str)
    print("  ✓ Parsed type is string")
    
    # Verify equality
    assert msg.type == parsed.type
    print("  ✓ Round-trip preserves type")


def test_invalid_message_type():
    """Test that invalid message types raise errors."""
    print("\nTesting invalid message type handling...")
    
    data = {
        "type": "invalid_type",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
    }
    
    try:
        parse_message(data)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unknown message type" in str(e)
        print(f"  ✓ Invalid type raises error: {e}")


def test_message_type_comparisons():
    """Test that message type comparisons work correctly."""
    print("\nTesting message type comparisons...")
    
    msg = ExecuteMessage(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        code="print('test')",
    )
    
    # String comparison should work
    assert msg.type == "execute"
    assert msg.type != "output"
    assert msg.type != "invalid"
    print("  ✓ String comparisons work")
    
    # Type should be string, not enum
    assert isinstance(msg.type, str)
    assert not isinstance(msg.type, MessageType)
    print("  ✓ Type is string, not enum")


async def test_worker_message_routing():
    """Test that worker correctly routes messages with string types."""
    print("\nTesting worker message routing simulation...")
    
    # Simulate message routing logic
    messages = [
        ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code="x = 1",
        ),
        InputResponseMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            data="user input",
            input_id=str(uuid.uuid4()),
        ),
        CheckpointMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            data=b"checkpoint",
            namespace_size=0,
            function_count=0,
            class_count=0,
            checkpoint_size=0,
        ),
        ShutdownMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            reason="test",
        ),
    ]
    
    for msg in messages:
        # Simulate worker routing logic with string comparisons
        if msg.type == "execute":
            assert isinstance(msg, ExecuteMessage)
            print("  ✓ Execute message routed correctly")
        elif msg.type == "input_response":
            assert isinstance(msg, InputResponseMessage)
            print("  ✓ Input response routed correctly")
        elif msg.type == "checkpoint":
            assert isinstance(msg, CheckpointMessage)
            print("  ✓ Checkpoint message routed correctly")
        elif msg.type == "shutdown":
            assert isinstance(msg, ShutdownMessage)
            print("  ✓ Shutdown message routed correctly")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Message Type Normalization Tests")
    print("=" * 60)
    
    try:
        test_parse_message_with_string_types()
        test_message_creation_types()
        test_serialization_consistency()
        test_invalid_message_type()
        test_message_type_comparisons()
        await test_worker_message_routing()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
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