"""HITL Input capability using Resonate promises in local mode."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from ..protocol.messages import InputMessage


class InputCapability:
    """
    Uses Resonate promises for HITL input request/response.
    """

    def __init__(self, resonate: Any, bridge: Any):
        self._resonate = resonate
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
        # Protocol uses InputResponseMessage with field 'data';
        # support legacy key 'input' for compatibility in tests.
        value = data.get("data") if isinstance(data, dict) else None
        if value is None and isinstance(data, dict):
            value = data.get("input")
        return str(value) if value is not None else ""
