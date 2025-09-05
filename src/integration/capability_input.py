from __future__ import annotations

"""HITL Input capability using Resonate promises in local mode."""

from typing import Any
import time
import uuid
import json

from ..protocol.messages import InputMessage


class InputCapability:
    """
    Uses Resonate promises for HITL input request/response.
    """

    def __init__(self, resonate: Any, transport: Any, bridge: Any):
        self._resonate = resonate
        self._transport = transport
        self._bridge = bridge

    async def request_input(self, prompt: str, execution_id: str) -> str:
        # Build input request message
        msg = InputMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            prompt=prompt,
            execution_id=execution_id,
            timeout=300.0,
        )
        # Send via bridge and await durable promise result
        promise = await self._bridge.send_request("input", execution_id, msg, timeout=300.0)
        result = await promise.result()  # SDK promise awaitable contract
        try:
            data = json.loads(result)
        except Exception:
            return ""
        return data.get("input", "")

