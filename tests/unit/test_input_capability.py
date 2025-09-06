import pytest
from unittest.mock import AsyncMock, Mock

from src.integration.capability_input import InputCapability


@pytest.mark.unit
@pytest.mark.asyncio
async def test_input_capability_request_roundtrip():
    # Arrange
    resonate = Mock()
    bridge = AsyncMock()

    # Promise mock with .result returning JSON string
    class Promise:
        async def result(self):
            # Match protocol shape: InputResponseMessage serialized
            return '{"type":"input_response","data":"hello","input_id":"rid"}'

    bridge.send_request.return_value = Promise()

    cap = InputCapability(resonate, bridge)

    # Act
    value = await cap.request_input("Prompt?", execution_id="E-1")

    # Assert
    assert value == "hello"
    # send_request called with capability id and message instance
    args, kwargs = bridge.send_request.await_args
    assert args[0] == "input"
    assert args[1] == "E-1"
    msg = args[2]
    assert hasattr(msg, "prompt") and msg.prompt == "Prompt?"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_input_capability_invalid_json_returns_empty():
    resonate = Mock()
    bridge = AsyncMock()

    class Promise:
        async def result(self):
            return "not-json"

    bridge.send_request.return_value = Promise()

    cap = InputCapability(resonate, bridge)
    value = await cap.request_input("Prompt?", execution_id="E-2")
    assert value == ""
