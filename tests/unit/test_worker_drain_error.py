"""Unit test for drain-timeout error shape emitted by worker.

Asserts the worker emits a single ErrorMessage with stable
exception_type and exception_message when output drain times out.
"""

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.subprocess.worker import SubprocessWorker
from src.subprocess.executor import OutputDrainTimeout
from src.protocol.messages import ExecuteMessage, ErrorMessage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_emits_stable_error_on_drain_timeout():
    transport = AsyncMock()

    # Prepare worker and a simple execute message
    worker = SubprocessWorker(transport, session_id="sess-1")
    exec_id = str(uuid.uuid4())
    msg = ExecuteMessage(id=exec_id, timestamp=time.time(), code="42")

    # Force OutputDrainTimeout during drain phase
    async def raise_timeout(self, timeout=None):  # noqa: ARG002
        raise OutputDrainTimeout("forced drain timeout for test")

    with patch("src.subprocess.executor.ThreadedExecutor.drain_outputs", new=raise_timeout):
        # Also avoid real pump start/join to keep the test fast and deterministic
        async def noop_start(self):  # noqa: ARG002
            return None

        with patch("src.subprocess.executor.ThreadedExecutor.start_output_pump", new=noop_start):
            # execute() internally starts a thread for execute_code; keep code trivial
            await worker.execute(msg)

    # Expect an ErrorMessage with stable type/message and correct execution_id
    sent = [call.args[0] for call in transport.send_message.call_args_list]
    errors = [m for m in sent if isinstance(m, ErrorMessage)]
    assert errors, "Expected an ErrorMessage when drain timeout occurs"
    # Last message should be the error for this execution
    err = errors[-1]
    assert err.execution_id == exec_id
    assert err.exception_type == "OutputDrainTimeout"
    assert err.exception_message == "Failed to drain all outputs before timeout"

