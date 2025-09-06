import json
import pytest

from types import SimpleNamespace
from src.integration.resonate_bridge import ResonateProtocolBridge
from src.integration.constants import input_promise_id
from src.protocol.messages import ExecuteMessage, ResultMessage, ErrorMessage, InputMessage, InputResponseMessage
import time


class PromiseStore:
    def __init__(self):
        self.created: dict[str, dict] = {}
        self.resolved: dict[str, str] = {}

    def create(self, id: str, timeout: int, data: str):
        prom = SimpleNamespace(_id=id)
        self.created[id] = {"timeout": timeout, "data": data, "promise": prom}
        return prom

    def resolve(self, id: str, data: str):
        self.resolved[id] = data


class Sender:
    def __init__(self):
        self.sent = []
    async def send_message(self, message):
        self.sent.append(message)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bridge_execute_result_error_correlation():
    # Arrange resonate-like with promises
    store = PromiseStore()
    resonate = SimpleNamespace(promises=store)
    sender = Sender()
    bridge = ResonateProtocolBridge(resonate, sender)

    # Send execute and map ExecuteMessage.id -> durable promise id
    exec_id = "E-123"
    exec_msg = ExecuteMessage(id=exec_id, timestamp=time.time(), code="1+1")
    await bridge.send_request("execute", exec_id, exec_msg, timeout=0.1, promise_id=f"exec:{exec_id}")

    # Route a result message and ensure resolution maps to provided promise id
    result_msg = ResultMessage(
        id="r1", timestamp=time.time(), value=2, repr="2", execution_id=exec_id, execution_time=0.01
    )
    assert await bridge.route_response(result_msg) is True
    payload = json.loads(store.resolved[f"exec:{exec_id}"])
    assert payload.get("type") == "result"
    assert payload.get("value") == 2

    # Send Input and map request.id -> bridge-created promise id
    input_msg = InputMessage(id="I-1", timestamp=time.time(), prompt="?", execution_id=exec_id, timeout=5.0)
    prom = await bridge.send_request("input", exec_id, input_msg)
    assert prom is not None

    # Route InputResponse and ensure it resolves the same promise
    resp = InputResponseMessage(id="IR-1", timestamp=time.time(), data="abc", input_id="I-1")
    assert await bridge.route_response(resp) is True
    payload = json.loads(store.resolved[input_promise_id(exec_id, "I-1")])
    assert payload.get("type") == "input_response"
