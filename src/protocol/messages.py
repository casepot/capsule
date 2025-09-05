from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    EXECUTE = "execute"
    OUTPUT = "output"
    INPUT = "input"
    INPUT_RESPONSE = "input_response"
    RESULT = "result"
    ERROR = "error"
    CHECKPOINT = "checkpoint"
    RESTORE = "restore"
    READY = "ready"
    HEARTBEAT = "heartbeat"
    SHUTDOWN = "shutdown"
    CANCEL = "cancel"
    INTERRUPT = "interrupt"


class StreamType(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"


class TransactionPolicy(str, Enum):
    COMMIT_ALWAYS = "commit_always"
    ROLLBACK_ON_FAILURE = "rollback_on_failure"
    ROLLBACK_ALWAYS = "rollback_always"


class BaseMessage(BaseModel):
    # Type field will be defined by subclasses with specific Literal values
    id: str = Field(description="Unique message identifier")
    timestamp: float = Field(description="Unix timestamp of message creation")


class ExecuteMessage(BaseMessage):
    type: Literal[MessageType.EXECUTE] = Field(default=MessageType.EXECUTE)
    code: str = Field(description="Python code to execute")
    transaction_id: Optional[str] = Field(
        default=None, description="Transaction ID for rollback support"
    )
    transaction_policy: TransactionPolicy = Field(
        default=TransactionPolicy.COMMIT_ALWAYS,
        description="Transaction commit/rollback policy",
    )
    capture_source: bool = Field(
        default=True, description="Whether to capture function/class sources"
    )


class OutputMessage(BaseMessage):
    type: Literal[MessageType.OUTPUT] = Field(default=MessageType.OUTPUT)
    data: str = Field(description="Output data")
    stream: StreamType = Field(description="Output stream type")
    execution_id: str = Field(description="ID of the execution that produced this output")


class InputMessage(BaseMessage):
    type: Literal[MessageType.INPUT] = Field(default=MessageType.INPUT)
    prompt: str = Field(description="Input prompt to display")
    execution_id: str = Field(description="ID of the execution requesting input")
    timeout: Optional[float] = Field(
        default=None, description="Timeout in seconds for input response"
    )


class InputResponseMessage(BaseMessage):
    type: Literal[MessageType.INPUT_RESPONSE] = Field(default=MessageType.INPUT_RESPONSE)
    data: str = Field(description="User input data")
    input_id: str = Field(description="ID of the input request being responded to")


class ResultMessage(BaseMessage):
    type: Literal[MessageType.RESULT] = Field(default=MessageType.RESULT)
    value: Any = Field(description="Result value (must be JSON-serializable)")
    repr: str = Field(description="String representation of the result")
    execution_id: str = Field(description="ID of the execution that produced this result")
    execution_time: float = Field(description="Execution time in seconds")


class ErrorMessage(BaseMessage):
    type: Literal[MessageType.ERROR] = Field(default=MessageType.ERROR)
    traceback: str = Field(description="Full traceback string")
    exception_type: str = Field(description="Exception class name")
    exception_message: str = Field(description="Exception message")
    execution_id: Optional[str] = Field(
        default=None, description="ID of the execution that caused the error"
    )


class CheckpointMessage(BaseMessage):
    type: Literal[MessageType.CHECKPOINT] = Field(default=MessageType.CHECKPOINT)
    # Creation trigger fields (local-mode slice):
    checkpoint_id: Optional[str] = Field(default=None, description="Checkpoint identifier")
    name: Optional[str] = Field(default=None, description="Checkpoint human-readable name")
    # Data fields (when sending a snapshot):
    data: Optional[bytes] = Field(default=None, description="Serialized checkpoint data")
    namespace_size: Optional[int] = Field(default=None, description="Number of items in namespace")
    function_count: Optional[int] = Field(default=None, description="Number of tracked functions")
    class_count: Optional[int] = Field(default=None, description="Number of tracked classes")
    checkpoint_size: Optional[int] = Field(default=None, description="Size of checkpoint in bytes")


class RestoreMessage(BaseMessage):
    type: Literal[MessageType.RESTORE] = Field(default=MessageType.RESTORE)
    # Reference by ID (local slice) or inline data
    checkpoint_id: Optional[str] = Field(
        default=None, description="Checkpoint identifier to restore"
    )
    data: Optional[bytes] = Field(default=None, description="Checkpoint data to restore")
    clear_existing: bool = Field(
        default=True, description="Whether to clear existing namespace before restore"
    )


class ReadyMessage(BaseMessage):
    type: Literal[MessageType.READY] = Field(default=MessageType.READY)
    session_id: str = Field(description="Session identifier")
    capabilities: list[str] = Field(
        default_factory=list, description="List of supported capabilities"
    )


class HeartbeatMessage(BaseMessage):
    type: Literal[MessageType.HEARTBEAT] = Field(default=MessageType.HEARTBEAT)
    memory_usage: int = Field(description="Current memory usage in bytes")
    cpu_percent: float = Field(description="CPU usage percentage")
    namespace_size: int = Field(description="Current namespace size")


class ShutdownMessage(BaseMessage):
    type: Literal[MessageType.SHUTDOWN] = Field(default=MessageType.SHUTDOWN)
    reason: str = Field(description="Shutdown reason")
    checkpoint: bool = Field(
        default=True, description="Whether to create checkpoint before shutdown"
    )


class CancelMessage(BaseMessage):
    type: Literal[MessageType.CANCEL] = Field(default=MessageType.CANCEL)
    execution_id: str = Field(description="ID of the execution to cancel")
    grace_timeout_ms: Optional[int] = Field(
        default=500, description="Grace period in milliseconds before hard cancel"
    )


class InterruptMessage(BaseMessage):
    type: Literal[MessageType.INTERRUPT] = Field(default=MessageType.INTERRUPT)
    execution_id: str = Field(description="ID of the execution to interrupt")
    force_restart: bool = Field(default=False, description="Force worker restart after interrupt")


Message = Union[
    ExecuteMessage,
    OutputMessage,
    InputMessage,
    InputResponseMessage,
    ResultMessage,
    ErrorMessage,
    CheckpointMessage,
    RestoreMessage,
    ReadyMessage,
    HeartbeatMessage,
    ShutdownMessage,
    CancelMessage,
    InterruptMessage,
]


def parse_message(data: dict[str, Any]) -> Message:
    """Parse a message from a dictionary.

    Args:
        data: Dictionary containing message data

    Returns:
        Parsed message object

    Raises:
        ValueError: If message type is unknown or data is invalid
    """
    message_type = data.get("type")
    if message_type is None:
        raise ValueError("Message type is missing")

    message_classes: dict[str, type[Message]] = {
        MessageType.EXECUTE.value: ExecuteMessage,
        MessageType.OUTPUT.value: OutputMessage,
        MessageType.INPUT.value: InputMessage,
        MessageType.INPUT_RESPONSE.value: InputResponseMessage,
        MessageType.RESULT.value: ResultMessage,
        MessageType.ERROR.value: ErrorMessage,
        MessageType.CHECKPOINT.value: CheckpointMessage,
        MessageType.RESTORE.value: RestoreMessage,
        MessageType.READY.value: ReadyMessage,
        MessageType.HEARTBEAT.value: HeartbeatMessage,
        MessageType.SHUTDOWN.value: ShutdownMessage,
        MessageType.CANCEL.value: CancelMessage,
        MessageType.INTERRUPT.value: InterruptMessage,
    }

    message_class = message_classes.get(message_type)
    if not message_class:
        raise ValueError(f"Unknown message type: {message_type}")

    return message_class(**data)
