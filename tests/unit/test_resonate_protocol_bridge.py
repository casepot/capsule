import pytest
import time
from unittest.mock import AsyncMock, Mock

from src.integration.resonate_bridge import ResonateProtocolBridge
from src.protocol.messages import InputMessage, InputResponseMessage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bridge_send_request_creates_promise_and_sends_message():
    # Arrange
    resonate = Mock()
    promise = AsyncMock()
    resonate.promises.create.return_value = promise
    transport = AsyncMock()
    bridge = ResonateProtocolBridge(resonate, transport)

    msg = InputMessage(id="m1", timestamp=time.time(), prompt="Enter:", execution_id="e1")

    # Act
    ret = await bridge.send_request("input", "e1", msg, timeout=0.5)

    # Assert
    assert ret is promise
    resonate.promises.create.assert_called_once()
    args, kwargs = resonate.promises.create.call_args
    assert kwargs["id"] == "e1:input:m1"
    # 0.5s -> 500ms
    assert kwargs["timeout"] == 500
    transport.send_message.assert_awaited_once_with(msg)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bridge_route_response_resolves_promise():
    resonate = Mock()
    transport = AsyncMock()
    bridge = ResonateProtocolBridge(resonate, transport)

    # Prime pending mapping via send_request
    req = InputMessage(id="abc", timestamp=time.time(), prompt="?", execution_id="e9")
    promise = AsyncMock()
    resonate.promises.create.return_value = promise
    await bridge.send_request("input", "e9", req)

    # Create response and route
    resp = InputResponseMessage(id="x", timestamp=time.time(), data="hello", input_id="abc")
    ok = await bridge.route_response(resp)
    assert ok is True
    resonate.promises.resolve.assert_called_once()
    rid = resonate.promises.resolve.call_args.kwargs["id"]
    assert rid == "e9:input:abc" or rid == "e9:input:abc"  # deterministic id

    # Unmatched returns False and does not raise
    resp2 = InputResponseMessage(id="y", timestamp=time.time(), data="hi", input_id="zzz")
    ok2 = await bridge.route_response(resp2)
    assert ok2 is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bridge_pending_cleanup_after_resolve():
    """After resolving a response, the bridge should clear pending mapping."""
    resonate = Mock()
    transport = AsyncMock()
    bridge = ResonateProtocolBridge(resonate, transport)

    # Prime with a request
    req = InputMessage(id="rid", timestamp=time.time(), prompt="?", execution_id="E")
    promise = AsyncMock()
    resonate.promises.create.return_value = promise
    await bridge.send_request("input", "E", req)

    # Ensure pending contains the request id
    assert "rid" in bridge._pending

    # Resolve via response
    resp = InputResponseMessage(id="x", timestamp=time.time(), data="ok", input_id="rid")
    await bridge.route_response(resp)

    # Pending must be cleared
    assert "rid" not in bridge._pending
