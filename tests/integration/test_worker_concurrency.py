"""Integration tests for worker concurrency and Busy guard behavior."""

import asyncio
import time
import uuid
import pytest

from typing import List

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, Message, OutputMessage, ResultMessage, ErrorMessage


@pytest.mark.integration
@pytest.mark.asyncio
async def test_busy_guard_rejects_second_execute():
    """Second concurrent execute should be rejected with Busy error, while the first completes normally."""
    session = Session()
    await session.start()

    async def collect(session: Session, exec_msg: ExecuteMessage) -> List[Message]:
        msgs: List[Message] = []
        async for m in session.execute(exec_msg, timeout=10.0):
            msgs.append(m)
        return msgs

    try:
        # Start a long-running execution to keep worker busy
        exec_id_1 = str(uuid.uuid4())
        long_code = """
import time
for i in range(20):
    print(f"tick {i}")
    time.sleep(0.05)
"done"
"""
        msg1 = ExecuteMessage(id=exec_id_1, timestamp=time.time(), code=long_code)
        task1 = asyncio.create_task(collect(session, msg1))

        # Give the worker a moment to start processing
        await asyncio.sleep(0.05)

        # Launch a second execution which should be rejected due to Busy guard
        exec_id_2 = str(uuid.uuid4())
        msg2 = ExecuteMessage(id=exec_id_2, timestamp=time.time(), code="42")
        msgs2 = await collect(session, msg2)

        # Verify Busy error for the second execution
        busy_errors = [m for m in msgs2 if isinstance(m, ErrorMessage)]
        assert len(busy_errors) == 1, f"Expected single Busy error, got {busy_errors}"
        assert busy_errors[0].exception_type == "Busy"
        assert busy_errors[0].execution_id == exec_id_2

        # First execution should complete normally with outputs then result
        msgs1 = await task1
        assert any(isinstance(m, ResultMessage) for m in msgs1), "First execution should complete"

        # No cross-talk: outputs/results should be tagged to the correct execution ids
        out1 = [m for m in msgs1 if isinstance(m, OutputMessage)]
        res1 = [m for m in msgs1 if isinstance(m, ResultMessage)]
        assert all(getattr(m, 'execution_id', exec_id_1) == exec_id_1 for m in out1 + res1)

        # Integration-level assertion: all non-output messages carry expected execution_id
        non_out1 = [m for m in msgs1 if not isinstance(m, OutputMessage)]
        assert all(
            getattr(m, 'execution_id', exec_id_1) == exec_id_1 for m in non_out1 if hasattr(m, 'execution_id')
        )

        # The second execution should not receive outputs or results
        assert not any(isinstance(m, OutputMessage) for m in msgs2)
        assert not any(isinstance(m, ResultMessage) for m in msgs2)

    finally:
        await session.shutdown()
