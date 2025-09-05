import pytest

from src.session.manager import Session
from src.protocol.messages import ResultMessage
import time
import uuid


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_message_interceptor_runs_before_routing(monkeypatch):
    session = Session()
    await session.start()

    try:
        called = {"count": 0, "last": None}

        def interceptor(msg):
            called["count"] += 1
            called["last"] = msg

        session.add_message_interceptor(interceptor)

        # Create a message with execution_id so it would normally be routed to a per-exec queue
        msg = ResultMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            value=1,
            repr="1",
            execution_id="exec-xyz",
            execution_time=0.01,
        )

        # Route the message directly (bypass transport loop)
        await session._route_message(msg)  # type: ignore[attr-defined]

        assert called["count"] == 1
        assert called["last"] is msg

    finally:
        await session.terminate()

