"""Resonate protocol bridge for local-mode durable promises.

Maps protocol requests to durable promises and routes responses back to
resolve those promises. This is a minimal local-mode adapter sufficient
for unit testing and single-process development.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from ..protocol.messages import (
    ErrorMessage,
    InputResponseMessage,
    Message,
    ResultMessage,
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
        # Background timeout tasks keyed by correlation key
        self._timeouts: dict[str, asyncio.Task[None]] = {}
        # Protects access to _pending and _timeouts
        self._lock = asyncio.Lock()
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
        promise_id: str | None = None,
    ) -> Any:
        """Create a durable promise and send a protocol message.

        TODO(correlation): Standardize promise id formats and correlation rules per
        spec. Execute/Result/Error should correlate via execution_id + message.id;
        Input/InputResponse uses input_id. The bridge should be the single source of
        truth for this mapping to keep durable correlation deterministic.
        """
        created_promise = None
        corr_key: str | None = None

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
                pid = (
                    promise_id or f"{execution_id}:{capability_id}:{getattr(message, 'id', 'req')}"
                )
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
            async with self._lock:
                self._pending[key] = str(promise_id)
                # Update high-water mark for observability breadcrumbs (local only)
                if len(self._pending) > self._pending_hwm:
                    self._pending_hwm = len(self._pending)

                # Schedule timeout rejection enrichment if requested
                effective_timeout = timeout if (timeout and timeout > 0) else 60.0
                if effective_timeout and effective_timeout > 0:
                    t = asyncio.create_task(
                        self._reject_on_timeout(
                            key,
                            str(promise_id),
                            capability_id=capability_id,
                            execution_id=execution_id,
                            timeout=effective_timeout,
                        )
                    )
                    # Track so we can cancel on resolve
                    self._timeouts[key] = t

        # Send message via session/sender
        await self._sender.send_message(message)

        # Return created promise if we created one (e.g., input). Execute path returns None.
        return created_promise

    async def route_response(self, message: Message) -> bool:
        corr = self._extract_correlation_key(message)
        if not corr:
            return False
        promise_id: str | None
        timeout_task: asyncio.Task[None] | None = None
        async with self._lock:
            promise_id = self._pending.pop(corr, None)
            # Cancel and forget any timeout task for this correlation
            timeout_task = self._timeouts.pop(corr, None)
        if timeout_task is not None:
            timeout_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await timeout_task
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
                try:
                    self._resonate.promises.reject(id=promise_id, error=payload)
                except Exception:
                    # Defensive: ignore benign already-settled errors
                    return True
            else:
                try:
                    self._resonate.promises.resolve(id=promise_id, data=payload)
                except Exception:
                    # Defensive: ignore benign already-settled errors
                    return True
            return True
        except Exception as e:
            # Swallow to avoid breaking receive loop, but log for diagnostics
            try:
                import structlog

                structlog.get_logger().debug("bridge_route_response_exception", error=str(e))
            except Exception:
                pass
            return False

    def _extract_correlation_key(self, message: Message) -> str | None:
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
            # Atomically verify and remove pending entry
            should_reject = False
            async with self._lock:
                current = self._pending.get(corr_key)
                if current == promise_id:
                    # Remove mapping and timeout task entries
                    self._pending.pop(corr_key, None)
                    self._timeouts.pop(corr_key, None)
                    should_reject = True
            if not should_reject:
                return
            err = {
                "type": "error",
                "exception_type": "TimeoutError",
                "exception_message": "Request timed out",
                "execution_id": execution_id,
                "capability": capability_id,
                "timeout": timeout,
                "request_id": corr_key,
            }
            try:
                self._resonate.promises.reject(id=promise_id, error=json.dumps(err))
            except Exception:
                # Ignore benign already-settled errors
                return
        except Exception:
            # Best-effort timeout handling; no raising
            return

    # Phase 3: Optional lightweight diagnostic getter
    def pending_high_water_mark(self) -> int:
        return self._pending_hwm
