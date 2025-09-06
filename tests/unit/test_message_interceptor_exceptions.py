import pytest
import time
import uuid

from src.session.manager import Session
from src.protocol.messages import ResultMessage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interceptor_exception_does_not_break_routing():
    session = Session()
    await session.start()

    try:
        # Add an interceptor that raises
        def bad_interceptor(msg):  # noqa: ARG001
            raise RuntimeError("interceptor boom")

        session.add_message_interceptor(bad_interceptor)

        # Create a message with execution_id to route to a per-execution queue
        exec_id = str(uuid.uuid4())
        msg = ResultMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            value=1,
            repr="1",
            execution_id=exec_id,
            execution_time=0.01,
        )

        # Route the message; exception must be handled internally and not propagate
        await session._route_message(msg)  # type: ignore[attr-defined]

        # Message should have been enqueued; in this path, it routes to the general queue
        qkey = "general"
        assert qkey in session._message_handlers  # type: ignore[attr-defined]
        queue = session._message_handlers[qkey]  # type: ignore[attr-defined]
        got = await queue.get()
        assert got is msg
    finally:
        await session.terminate()
