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
    type: MessageType
    id: str = Field(description="Unique message identifier")
    timestamp: float = Field(description="Unix timestamp of message creation")


class ExecuteMessage(BaseMessage):
    type: Literal["execute"] = "execute"
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
    type: Literal["output"] = "output"
    data: str = Field(description="Output data")
    stream: StreamType = Field(description="Output stream type")
    execution_id: str = Field(description="ID of the execution that produced this output")


class InputMessage(BaseMessage):
    type: Literal["input"] = "input"
    prompt: str = Field(description="Input prompt to display")
    execution_id: str = Field(description="ID of the execution requesting input")
    timeout: Optional[float] = Field(
        default=None, description="Timeout in seconds for input response"
    )


class InputResponseMessage(BaseMessage):
    type: Literal["input_response"] = "input_response"
    data: str = Field(description="User input data")
    input_id: str = Field(description="ID of the input request being responded to")


class ResultMessage(BaseMessage):
    type: Literal["result"] = "result"
    value: Any = Field(description="Result value (must be JSON-serializable)")
    repr: str = Field(description="String representation of the result")
    execution_id: str = Field(description="ID of the execution that produced this result")
    execution_time: float = Field(description="Execution time in seconds")


class ErrorMessage(BaseMessage):
    type: Literal["error"] = "error"
    traceback: str = Field(description="Full traceback string")
    exception_type: str = Field(description="Exception class name")
    exception_message: str = Field(description="Exception message")
    execution_id: Optional[str] = Field(
        default=None, description="ID of the execution that caused the error"
    )


class CheckpointMessage(BaseMessage):
    type: Literal["checkpoint"] = "checkpoint"
    data: bytes = Field(description="Serialized checkpoint data")
    namespace_size: int = Field(description="Number of items in namespace")
    function_count: int = Field(description="Number of tracked functions")
    class_count: int = Field(description="Number of tracked classes")
    checkpoint_size: int = Field(description="Size of checkpoint in bytes")


class RestoreMessage(BaseMessage):
    type: Literal["restore"] = "restore"
    data: bytes = Field(description="Checkpoint data to restore")
    clear_existing: bool = Field(
        default=True, description="Whether to clear existing namespace before restore"
    )


class ReadyMessage(BaseMessage):
    type: Literal["ready"] = "ready"
    session_id: str = Field(description="Session identifier")
    capabilities: list[str] = Field(
        default_factory=list, description="List of supported capabilities"
    )


class HeartbeatMessage(BaseMessage):
    type: Literal["heartbeat"] = "heartbeat"
    memory_usage: int = Field(description="Current memory usage in bytes")
    cpu_percent: float = Field(description="CPU usage percentage")
    namespace_size: int = Field(description="Current namespace size")


class ShutdownMessage(BaseMessage):
    type: Literal["shutdown"] = "shutdown"
    reason: str = Field(description="Shutdown reason")
    checkpoint: bool = Field(default=True, description="Whether to create checkpoint before shutdown")


class CancelMessage(BaseMessage):
    type: Literal["cancel"] = "cancel"
    execution_id: str = Field(description="ID of the execution to cancel")
    grace_timeout_ms: Optional[int] = Field(
        default=500, description="Grace period in milliseconds before hard cancel"
    )


class InterruptMessage(BaseMessage):
    type: Literal["interrupt"] = "interrupt"
    execution_id: str = Field(description="ID of the execution to interrupt")
    force_restart: bool = Field(
        default=False, description="Force worker restart after interrupt"
    )


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
    
    message_classes = {
        "execute": ExecuteMessage,
        "output": OutputMessage,
        "input": InputMessage,
        "input_response": InputResponseMessage,
        "result": ResultMessage,
        "error": ErrorMessage,
        "checkpoint": CheckpointMessage,
        "restore": RestoreMessage,
        "ready": ReadyMessage,
        "heartbeat": HeartbeatMessage,
        "shutdown": ShutdownMessage,
        "cancel": CancelMessage,
        "interrupt": InterruptMessage,
    }
    
    message_class = message_classes.get(message_type)
    if not message_class:
        raise ValueError(f"Unknown message type: {message_type}")
    
    return message_class(**data)