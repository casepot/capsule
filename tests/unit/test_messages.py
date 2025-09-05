"""Unit tests for protocol messages."""

import pytest
import time
import uuid
from src.protocol.messages import (
    ExecuteMessage,
    ResultMessage,
    OutputMessage,
    ErrorMessage,
    HeartbeatMessage,
    ReadyMessage,
    CancelMessage,
    InputMessage,
    InputResponseMessage,
    MessageType,
    parse_message,
    CheckpointMessage,
    RestoreMessage,
)


@pytest.mark.unit
class TestMessageCreation:
    """Test message creation and validation."""
    
    def test_execute_message_creation(self):
        """Test creating an execute message."""
        msg = ExecuteMessage(
            id="test-123",
            timestamp=time.time(),
            code="print('hello')",
        )
        assert msg.type == MessageType.EXECUTE
        assert msg.code == "print('hello')"
        assert msg.id == "test-123"
    
    def test_result_message_creation(self):
        """Test creating a result message."""
        msg = ResultMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            execution_id="exec-123",
            value=42,
            repr="42",
            execution_time=0.5,
        )
        assert msg.type == MessageType.RESULT
        assert msg.value == 42
        assert msg.repr == "42"
    
    def test_error_message_creation(self):
        """Test creating an error message."""
        msg = ErrorMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            execution_id="exec-123",
            exception_type="ValueError",
            exception_message="Invalid value",
            traceback="Traceback...",
        )
        assert msg.type == MessageType.ERROR
        assert msg.exception_type == "ValueError"
        assert msg.exception_message == "Invalid value"


@pytest.mark.unit
class TestMessageParsing:
    """Test message parsing and deserialization."""
    
    def test_parse_execute_message(self):
        """Test parsing an execute message from dict."""
        data = {
            "type": "execute",
            "id": "test-123",
            "timestamp": time.time(),
            "code": "x = 10",
        }
        msg = parse_message(data)
        assert isinstance(msg, ExecuteMessage)
        assert msg.code == "x = 10"
    
    def test_parse_unknown_message_type(self):
        """Test parsing unknown message type raises error."""
        data = {
            "type": "unknown",
            "id": "test-123",
            "timestamp": time.time(),
        }
        with pytest.raises(ValueError):
            parse_message(data)
    
    def test_parse_malformed_message(self):
        """Test parsing malformed message raises error."""
        data = {
            "type": "execute",
            # Missing required fields
        }
        with pytest.raises(Exception):  # Pydantic validation error
            parse_message(data)


@pytest.mark.unit
class TestMessageSerialization:
    """Test message serialization."""
    
    def test_message_to_dict(self):
        """Test converting message to dictionary."""
        msg = HeartbeatMessage(
            id="test-123",
            timestamp=time.time(),
            memory_usage=1024 * 1024,
            cpu_percent=25.0,
            namespace_size=10,
        )
        data = msg.model_dump()
        assert data["type"] == "heartbeat"
        assert data["id"] == "test-123"
        assert "timestamp" in data
    
    def test_message_json_serialization(self):
        """Test JSON serialization of messages."""
        msg = OutputMessage(
            id="test-123",
            timestamp=time.time(),
            execution_id="exec-123",
            data="Hello, World!",
            stream="stdout",
        )
        json_str = msg.model_dump_json()
        assert "Hello, World!" in json_str
        assert "stdout" in json_str


@pytest.mark.unit
def test_checkpoint_restore_minimal_fields():
    """Checkpoint/Restore should accept minimal fields (per spec)."""
    # Minimal checkpoint: id, timestamp, checkpoint_id
    cp = CheckpointMessage(id="cp1", timestamp=time.time(), checkpoint_id="abc")
    assert cp.checkpoint_id == "abc"
    # Minimal restore by id
    r1 = RestoreMessage(id="rs1", timestamp=time.time(), checkpoint_id="abc")
    assert r1.checkpoint_id == "abc"
    # Minimal restore by data
    r2 = RestoreMessage(id="rs2", timestamp=time.time(), data=b"blob")
    assert r2.data == b"blob"
