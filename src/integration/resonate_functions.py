from __future__ import annotations

"""Resonate durable function registrations.

Provides a minimal durable_execute function wired for local mode using
AsyncExecutor via DI factory. The function follows generator-style
durable function semantics expected by the Resonate SDK.
"""

from typing import Any, Callable, Generator
import time
import json
from ..protocol.messages import ExecuteMessage
from .types import DurableResult


def register_executor_functions(resonate: Any) -> Any:
    """Register durable executor-related functions with Resonate.

    Registers:
    - durable_execute v1.0.0
    """

    @resonate.register(name="durable_execute", version=1)  # type: ignore[misc]
    def durable_execute(ctx: Any, args: dict[str, Any]) -> Generator[Any, Any, DurableResult]:
        """
        Promise-first durable execution using the protocol bridge.

        Flow:
          - Create stable promise id (exec:{execution_id}) via ctx.promise
          - Send ExecuteMessage via bridge (mapped to that promise)
          - Await resolution via the promise; parse result payload safely

        No event loop creation or management occurs here.
        """
        code = args["code"]
        execution_id = args["execution_id"]

        # Pre-execution checkpoint (if available)
        if hasattr(ctx, "checkpoint"):
            yield ctx.checkpoint(
                "pre_execution",
                {"execution_id": execution_id, "code_len": len(code)},
            )

        # Prepare durable promise and bridge
        bridge = ctx.get_dependency("protocol_bridge")
        timeout = float(getattr(getattr(ctx, "config", None), "tla_timeout", 30.0))
        promise_id = f"exec:{execution_id}"

        # Register/create promise in durable layer
        promise = yield ctx.promise(id=promise_id)

        # Build and send Execute request; correlate request-id to promise-id
        exec_msg = ExecuteMessage(
            id=execution_id,
            timestamp=time.time(),
            code=code,
            capture_source=True,
        )
        # Bridge returns a promise for some capabilities; not needed for execute
        yield bridge.send_request(
            "execute", execution_id, exec_msg, timeout=timeout, promise_id=promise_id
        )

        # Await durable resolution (may raise on rejection)
        try:
            raw = yield promise
        except Exception as e:
            # Promise rejected -> surface structured error with context
            err = RuntimeError("durable_execute rejected")
            if hasattr(err, "add_note"):
                try:
                    err.add_note(f"Execution ID: {execution_id}")
                    err.add_note(str(e))
                except Exception:
                    pass
            raise err

        result_value: Any = None
        try:
            payload = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
            # Expect ResultMessage/ErrorMessage shape
            typ = payload.get("type") if isinstance(payload, dict) else None
            if typ == "result" and isinstance(payload, dict):
                result_value = payload.get("value")
                # Fallback to repr if value not serializable
                if result_value is None:
                    result_value = payload.get("repr")
            elif typ == "error" or (isinstance(payload, dict) and "exception_message" in payload):
                # Attach structured context where supported and raise
                msg = payload.get("exception_message", "Execution error")
                exc = RuntimeError(msg)
                if hasattr(exc, "add_note"):
                    try:
                        exc.add_note(f"Execution ID: {execution_id}")
                        exc.add_note(payload.get("traceback", ""))
                    except Exception:
                        pass
                raise exc
            else:
                # Unknown payload type; return as-is for diagnostics
                result_value = payload
        except Exception as e:  # pragma: no cover - defensive path
            if hasattr(e, "add_note"):
                e.add_note(f"Execution ID: {execution_id}")
                e.add_note(f"Failed to parse promise payload of type {type(raw)}")
            raise

        # Post-execution checkpoint (if available)
        if hasattr(ctx, "checkpoint"):
            yield ctx.checkpoint("post_execution", {"execution_id": execution_id})

        return {"result": result_value, "execution_id": execution_id}

    # Expose handle for tests and local callers
    try:
        setattr(resonate, "capsule_durable_execute", durable_execute)
    except Exception:
        pass
    # Return the decorated function (supports .run() on real SDKs)
    return durable_execute
