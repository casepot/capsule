import pytest
import time
import uuid

from src.session.manager import Session
from src.protocol.messages import ResultMessage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_message_does_not_invoke_interceptors():
    """Interceptors must be invoked in the receive loop only, not in _route_message."""
    session = Session()
    await session.start()
    try:
        calls = {"count": 0}

        def interceptor(_msg):
            calls["count"] += 1

        session.add_message_interceptor(interceptor)

        # Manually route a message; interceptor should NOT be called here
        exec_id = str(uuid.uuid4())
        msg = ResultMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            value=1,
            repr="1",
            execution_id=exec_id,
            execution_time=0.01,
        )
        await session._route_message(msg)  # type: ignore[attr-defined]

        assert calls["count"] == 0
    finally:
        await session.terminate()

