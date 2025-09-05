from __future__ import annotations

"""Resonate protocol bridge for local-mode durable promises.

Maps protocol requests to durable promises and routes responses back to
resolve those promises. This is a minimal local-mode adapter sufficient
for unit testing and single-process development.
"""

from typing import Any, Optional
import json

from ..protocol.messages import (
    InputResponseMessage,
    Message,
)


class ResonateProtocolBridge:
    """
    Maps protocol requests to durable promises (local mode).
    - send_request(...)-> Promise: creates durable promise (id: f"{execution_id}:{capability_id}:{message.id}"),
      sends message over transport, returns an awaitable promise.
    - route_response(message)-> bool: resolves promise; False if unmatched.
    """

    def __init__(self, resonate: Any, transport: Any):
        self._resonate = resonate
        self._transport = transport
        # Track request-id -> promise-id for correlation
        self._pending: dict[str, str] = {}

    async def send_request(
        self,
        capability_id: str,
        execution_id: str,
        message: Message,
        timeout: float | None = None,
    ):
        """Create a durable promise and send a protocol message.

        TODO(correlation): Standardize promise id formats and correlation rules per
        spec. Execute/Result/Error should correlate via execution_id + message.id;
        Input/InputResponse uses input_id. The bridge should be the single source of
        truth for this mapping to keep durable correlation deterministic.
        """
        promise_id = f"{execution_id}:{capability_id}:{message.id}"
        # Timeout in milliseconds; default 30s
        timeout_ms = int((timeout or 30.0) * 1000)
        promise = self._resonate.promises.create(
            id=promise_id,
            timeout=timeout_ms,
            data="{}",
        )
        # Record mapping to resolve later
        self._pending[message.id] = promise_id
        # Send message over transport
        await self._transport.send_message(message)
        return promise  # awaitable via SDK (promise.result())

    async def route_response(self, message: Message) -> bool:
        corr = self._extract_correlation_key(message)
        if not corr:
            return False
        promise_id = self._pending.pop(corr, None)
        if not promise_id:
            return False
        try:
            # Serialize message to JSON string
            payload: str
            if hasattr(message, "model_dump_json"):
                payload = message.model_dump_json()
            elif hasattr(message, "model_dump"):
                payload = json.dumps(message.model_dump(mode="json"))
            else:
                # Fallback: best-effort generic conversion
                payload = json.dumps(getattr(message, "__dict__", {}))
            self._resonate.promises.resolve(id=promise_id, data=payload)
            return True
        except Exception:
            return False

    def _extract_correlation_key(self, message: Message) -> Optional[str]:
        """Return the request-side message.id used to create the promise.

        For InputResponseMessage, the correlation is `input_id` which is the
        request InputMessage.id. For other message types in this slice, we
        only support explicit mappings created in send_request.

        TODO(extend): Add Execute/Result/Error correlation when result/error messages
        flow back over the same transport. That mapping should most likely be
        `f"{execution_id}:execute:{execute_message.id}"` and resolved when receiving
        ResultMessage/ErrorMessage for that execution.
        """
        if isinstance(message, InputResponseMessage):
            return message.input_id
        # Unknown mapping for this vertical slice
        # Could be extended to support Result/Error tied to ExecuteMessage
        return None
