"""Message-related test fixtures."""

import time
import uuid
from typing import Any

from src.protocol.messages import (
    ExecuteMessage,
    CancelMessage,
    InputResponseMessage,
    ShutdownMessage,
    MessageType,
)


class MessageFactory:
    """Factory for creating test messages."""
    
    @staticmethod
    def execute(code: str, **kwargs) -> ExecuteMessage:
        """Create an execute message."""
        return ExecuteMessage(
            id=kwargs.get("id", str(uuid.uuid4())),
            timestamp=kwargs.get("timestamp", time.time()),
            code=code,
        )
    
    @staticmethod
    def cancel(execution_id: str | None = None) -> CancelMessage:
        """Create a cancel message."""
        return CancelMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            execution_id=execution_id,
        )
    
    @staticmethod
    def input_response(text: str, execution_id: str | None = None) -> InputResponseMessage:
        """Create an input response message."""
        return InputResponseMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            execution_id=execution_id,
            text=text,
        )
    
    @staticmethod
    def shutdown() -> ShutdownMessage:
        """Create a shutdown message."""
        return ShutdownMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
        )


def assert_message_type(message: Any, expected_type: str | MessageType) -> None:
    """Assert that a message has the expected type."""
    if isinstance(expected_type, str):
        assert message.type == expected_type
    else:
        assert message.type == expected_type.value


def assert_output_contains(messages: list, expected: str) -> None:
    """Assert that output messages contain expected text."""
    outputs = [
        msg.data for msg in messages 
        if msg.type == MessageType.OUTPUT
    ]
    full_output = "".join(outputs)
    assert expected in full_output, f"Expected '{expected}' not found in output: {full_output}"


def assert_result_value(messages: list, expected: Any) -> None:
    """Assert that result message has expected value."""
    results = [
        msg for msg in messages 
        if msg.type == MessageType.RESULT
    ]
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    assert results[0].value == expected


def assert_error_type(messages: list, expected_type: str) -> None:
    """Assert that error message has expected exception type."""
    errors = [
        msg for msg in messages 
        if msg.type == MessageType.ERROR
    ]
    assert len(errors) >= 1, "No error messages found"
    assert expected_type in errors[0].exception_type