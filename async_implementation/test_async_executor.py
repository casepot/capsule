
# tests/test_async_executor.py
import asyncio
import pytest

from src.subprocess.async_executor import AsyncExecutor
from src.subprocess.code_analyzer import CodeAnalyzer
from messages import OutputMessage, ResultMessage, InputMessage  # stub import
from types import SimpleNamespace

class DummyTransport:
    def __init__(self):
        self.out = []
        self.inp_waiters = {}

    async def send_message(self, msg):
        # Just record; in real system, messages go to the client
        self.out.append(msg)

@pytest.mark.asyncio
async def test_top_level_await():
    ns = {}
    transport = DummyTransport()
    ex = AsyncExecutor(transport, "exec-1", ns)
    code = "import asyncio\ndata = await asyncio.sleep(0.01, result='test_data')\ndata"
    result = await ex.execute(code)
    assert result == "test_data"
    assert ns["data"] == "test_data"
    assert ns["_"] == "test_data"

@pytest.mark.asyncio
async def test_blocking_io_fallback():
    ns = {}
    transport = DummyTransport()
    ex = AsyncExecutor(transport, "exec-2", ns)
    code = "import time\ntime.sleep(0.05)\n'completed'"
    result = await ex.execute(code)
    assert result == "completed"

@pytest.mark.asyncio
async def test_async_function_definition_and_call():
    ns = {"asyncio": asyncio}
    transport = DummyTransport()
    ex = AsyncExecutor(transport, "exec-3", ns)
    code1 = "import asyncio\nasync def fetch():\n    await asyncio.sleep(0.01)\n    return {'data':'ok'}"
    await ex.execute(code1)

    code2 = "result = await fetch()\nresult"
    result = await ex.execute(code2)
    assert result == {"data": "ok"}
