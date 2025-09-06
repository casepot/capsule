import pytest
import time
from unittest.mock import AsyncMock, Mock
import asyncio

from src.integration.resonate_bridge import ResonateProtocolBridge
from src.integration.constants import input_promise_id
from src.protocol.messages import InputMessage, InputResponseMessage, ExecuteMessage, ResultMessage, ErrorMessage


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
    assert kwargs["id"] == input_promise_id("e1", "m1")
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
    assert rid == input_promise_id("e9", "abc")  # deterministic id

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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bridge_rejects_on_error_message_and_cleans_pending():
    class Store:
        def __init__(self):
            self.rejected = {}
            self.resolved = {}
        def create(self, id: str, timeout: int, data: str):
            return object()
        def resolve(self, id: str, data: str):
            self.resolved[id] = data
        def reject(self, id: str, error: str):
            self.rejected[id] = error

    store = Store()
    resonate = type('R', (), {'promises': store})()
    class S:
        async def send_message(self, m):
            return None
    sender = S()
    bridge = ResonateProtocolBridge(resonate, sender)

    exec_id = "E-42"
    exec_msg = ExecuteMessage(id=exec_id, timestamp=time.time(), code="1/0")
    await bridge.send_request("execute", exec_id, exec_msg, timeout=0.1, promise_id=f"exec:{exec_id}")

    # Route an error and ensure rejection
    err = ErrorMessage(id="e1", timestamp=time.time(), traceback="tb", exception_type="ZeroDivisionError", exception_message="boom", execution_id=exec_id)
    ok = await bridge.route_response(err)
    assert ok is True
    assert f"exec:{exec_id}" in store.rejected
    assert exec_id not in bridge._pending


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bridge_timeout_enriches_rejection_payload():
    class Store:
        def __init__(self):
            self.rejected = {}
        def create(self, id: str, timeout: int, data: str):
            return object()
        def reject(self, id: str, error: str):
            self.rejected[id] = error

    resonate = type('R', (), {'promises': Store()})()
    class S2:
        async def send_message(self, m):
            return None
    sender = S2()
    bridge = ResonateProtocolBridge(resonate, sender)

    # Short timeout to trigger background reject
    req = InputMessage(id="I1", timestamp=time.time(), prompt="?", execution_id="X", timeout=0.01)
    await bridge.send_request("input", "X", req, timeout=0.05)
    # Allow timeout task to run
    await asyncio.sleep(0.06)
    # One rejection should have been recorded
    rejected = resonate.promises.rejected
    assert len(rejected) == 1
    payload = list(rejected.values())[0]
    assert 'timeout' in payload and 'X' in payload and 'input' in payload
