from __future__ import annotations

"""Resonate protocol bridge for local-mode durable promises.

Maps protocol requests to durable promises and routes responses back to
resolve those promises. This is a minimal local-mode adapter sufficient
for unit testing and single-process development.
"""

from typing import Any, Optional
import asyncio
import json

from ..protocol.messages import (
    ErrorMessage,
    InputResponseMessage,
    ResultMessage,
    Message,
)
from .constants import execution_promise_id, input_promise_id


class ResonateProtocolBridge:
    """
    Maps protocol requests to durable promises (local mode).
    - send_request(...)-> Promise: creates durable promise (id: f"{execution_id}:{capability_id}:{message.id}"),
      sends message over transport, returns an awaitable promise.
    - route_response(message)-> bool: resolves promise; False if unmatched.
    """

    def __init__(self, resonate: Any, session_or_sender: Any):
        """Bridge that correlates protocol requests with durable promises.

        Args:
            resonate: Resonate instance providing promises API
            session_or_sender: Object with `send_message(Message)` used to send
                protocol messages (typically the Session). This preserves the
                single-loop invariant by avoiding additional readers.
        """
        self._resonate = resonate
        self._sender = session_or_sender
        # Map correlation key -> durable promise id
        # Keys:
        #   - Execute: ExecuteMessage.id (equals execution_id in worker)
        #   - Input:   InputMessage.id
        #   - Others as extended
        self._pending: dict[str, str] = {}
        # TODO(Phase 3): expose a lightweight metric for the high-water mark
        # of pending correlations to observe load/backpressure trends without
        # adding runtime overhead. For now, track the value locally.
        self._pending_hwm: int = 0

    async def send_request(
        self,
        capability_id: str,
        execution_id: str,
        message: Message,
        timeout: float | None = None,
        *,
        promise_id: Optional[str] = None,
    ) -> Any:
        """Create a durable promise and send a protocol message.

        TODO(correlation): Standardize promise id formats and correlation rules per
        spec. Execute/Result/Error should correlate via execution_id + message.id;
        Input/InputResponse uses input_id. The bridge should be the single source of
        truth for this mapping to keep durable correlation deterministic.
        """
        created_promise = None
        corr_key: Optional[str] = None

        if capability_id == "execute":
            # Promise should already be created by durable function via ctx.promise
            # Use provided promise_id; correlate by ExecuteMessage.id (== execution_id in worker)
            if not promise_id:
                # Deterministic id per spec via centralized constant
                promise_id = execution_promise_id(execution_id)
            corr_key = getattr(message, "id", None)
        else:
            # Create a new durable promise for other capabilities (e.g., input)
            if capability_id == "input":
                # Deterministic input promise id using centralized constants
                pid = promise_id or input_promise_id(execution_id, getattr(message, "id", "req"))
            else:
                # Generic, but still deterministic fallback for future caps
                pid = promise_id or f"{execution_id}:{capability_id}:{getattr(message, 'id', 'req')}"
            timeout_ms = int((timeout or 30.0) * 1000)
            created_promise = self._resonate.promises.create(
                id=pid,
                timeout=timeout_ms,
                data="{}",
            )
            promise_id = pid
            corr_key = getattr(message, "id", None)

        if corr_key:
            key = str(corr_key)
            self._pending[key] = str(promise_id)
            # Update high-water mark for observability breadcrumbs (local only)
            if len(self._pending) > self._pending_hwm:
                self._pending_hwm = len(self._pending)

            # Schedule timeout rejection enrichment if requested
            if timeout and timeout > 0:
                asyncio.create_task(
                    self._reject_on_timeout(
                        key,
                        str(promise_id),
                        capability_id=capability_id,
                        execution_id=execution_id,
                        timeout=timeout,
                    )
                )

        # Send message via session/sender
        await self._sender.send_message(message)

        # Return created promise if we created one (e.g., input). Execute path returns None.
        return created_promise

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
            # Determine resolve vs reject semantics
            if isinstance(message, ErrorMessage):
                self._resonate.promises.reject(id=promise_id, error=payload)
            else:
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
        if isinstance(message, ResultMessage):
            return message.execution_id
        if isinstance(message, ErrorMessage):
            # Error may include execution_id when tied to an execution
            return message.execution_id or None
        return None

    async def _reject_on_timeout(
        self,
        corr_key: str,
        promise_id: str,
        *,
        capability_id: str,
        execution_id: str,
        timeout: float,
    ) -> None:
        """Reject a promise if it remains pending after timeout seconds.

        Adds structured context to the rejection payload.
        """
        try:
            await asyncio.sleep(timeout)
            # Only reject if still pending
            if self._pending.get(corr_key) != promise_id:
                return
            # Clean up mapping before rejection to avoid leaks
            self._pending.pop(corr_key, None)
            err = {
                "type": "error",
                "exception_type": "TimeoutError",
                "exception_message": "Request timed out",
                "execution_id": execution_id,
                "capability": capability_id,
                "timeout": timeout,
                "request_id": corr_key,
            }
            self._resonate.promises.reject(id=promise_id, error=json.dumps(err))
        except Exception:
            # Best-effort timeout handling; no raising
            return
