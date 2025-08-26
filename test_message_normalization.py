#!/usr/bin/env python3
"""Test to demonstrate message type normalization issue."""

import json
import msgpack
from src.protocol.messages import MessageType, ExecuteMessage, parse_message


def test_message_type_inconsistency():
    """Test that demonstrates the message type inconsistency issue."""
    
    # Create a message using the class directly
    execute_msg = ExecuteMessage(
        id="test-1",
        timestamp=1234567890.0,
        code="print('hello')"
    )
    
    print(f"Direct ExecuteMessage creation:")
    print(f"  message.type = {execute_msg.type!r}")
    print(f"  type(message.type) = {type(execute_msg.type)}")
    print(f"  message.type == MessageType.EXECUTE = {execute_msg.type == MessageType.EXECUTE}")
    print(f"  message.type == 'execute' = {execute_msg.type == 'execute'}")
    print()
    
    # Simulate what happens when we parse a message from JSON
    json_data = {
        "type": "execute",
        "id": "test-2",
        "timestamp": 1234567890.0,
        "code": "print('hello')"
    }
    
    parsed_from_json = parse_message(json_data)
    print(f"Parsed from JSON dict with string type:")
    print(f"  message.type = {parsed_from_json.type!r}")
    print(f"  type(message.type) = {type(parsed_from_json.type)}")
    print(f"  message.type == MessageType.EXECUTE = {parsed_from_json.type == MessageType.EXECUTE}")
    print(f"  message.type == 'execute' = {parsed_from_json.type == 'execute'}")
    print()
    
    # Simulate what happens with msgpack (which preserves the string)
    msgpack_data = msgpack.packb(json_data, use_bin_type=True)
    unpacked_data = msgpack.unpackb(msgpack_data, raw=False, strict_map_key=False)
    
    parsed_from_msgpack = parse_message(unpacked_data)
    print(f"Parsed from msgpack:")
    print(f"  message.type = {parsed_from_msgpack.type!r}")
    print(f"  type(message.type) = {type(parsed_from_msgpack.type)}")
    print(f"  message.type == MessageType.EXECUTE = {parsed_from_msgpack.type == MessageType.EXECUTE}")
    print(f"  message.type == 'execute' = {parsed_from_msgpack.type == 'execute'}")
    print()
    
    # Now test with Enum value in the data
    json_data_with_enum = {
        "type": MessageType.EXECUTE,
        "id": "test-3",
        "timestamp": 1234567890.0,
        "code": "print('hello')"
    }
    
    parsed_with_enum = parse_message(json_data_with_enum)
    print(f"Parsed from dict with MessageType enum:")
    print(f"  message.type = {parsed_with_enum.type!r}")
    print(f"  type(message.type) = {type(parsed_with_enum.type)}")
    print(f"  message.type == MessageType.EXECUTE = {parsed_with_enum.type == MessageType.EXECUTE}")
    print(f"  message.type == 'execute' = {parsed_with_enum.type == 'execute'}")
    print()
    
    # Show the issue: MessageType enum is both a str and an enum
    print(f"MessageType.EXECUTE details:")
    print(f"  value = {MessageType.EXECUTE!r}")
    print(f"  type = {type(MessageType.EXECUTE)}")
    print(f"  MessageType.EXECUTE == 'execute' = {MessageType.EXECUTE == 'execute'}")
    print(f"  isinstance(MessageType.EXECUTE, str) = {isinstance(MessageType.EXECUTE, str)}")


if __name__ == "__main__":
    test_message_type_inconsistency()