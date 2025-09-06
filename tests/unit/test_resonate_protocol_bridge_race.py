import pytest
import asyncio
import time

from src.integration.resonate_bridge import ResonateProtocolBridge
from src.protocol.messages import InputMessage, InputResponseMessage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bridge_resolve_cancels_timeout_and_prevents_race():
    class Store:
        def __init__(self):
            self.resolved = {}
            self.rejected = {}
        def create(self, id: str, timeout: int, data: str):
            return object()
        def resolve(self, id: str, data: str):
            # Simulate idempotent resolve
            self.resolved[id] = data
        def reject(self, id: str, error: str):
            # Reject should not fire after resolve
            self.rejected[id] = error

    class Sender:
        async def send_message(self, m):
            return None

    resonate = type('R', (), {'promises': Store()})()
    bridge = ResonateProtocolBridge(resonate, Sender())

    # Issue a request with a short timeout
    req = InputMessage(id="rid", timestamp=time.time(), prompt="?", execution_id="E", timeout=0.05)
    await bridge.send_request("input", "E", req, timeout=0.05)

    # Race: deliver response before (or just as) timeout fires
    await asyncio.sleep(0.01)
    resp = InputResponseMessage(id="x", timestamp=time.time(), data="ok", input_id="rid")
    ok = await bridge.route_response(resp)
    assert ok is True

    # Wait beyond timeout to ensure background task would have fired if not cancelled
    await asyncio.sleep(0.06)

    # Ensure no rejection after resolve and internal maps are cleaned
    assert resonate.promises.rejected == {}
    assert "rid" not in bridge._pending
    assert "rid" not in bridge._timeouts

