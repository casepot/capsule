from __future__ import annotations

"""Resonate durable function registrations.

Provides a minimal durable_execute function wired for local mode using
AsyncExecutor via DI factory. The function follows generator-style
durable function semantics expected by the Resonate SDK.
"""

from typing import Any, Generator
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
        # Normalize raw into a Python object if JSON-like; otherwise leave as-is
        payload: Any
        if isinstance(raw, (bytes, bytearray)):
            try:
                payload = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                payload = raw.decode("utf-8", errors="replace")
        elif isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except Exception:
                payload = raw
        else:
            payload = raw

        # Expect ResultMessage/ErrorMessage shapes but be tolerant of other types
        if isinstance(payload, dict):
            typ = payload.get("type")
            if typ == "result":
                result_value = payload.get("value")
                if result_value is None:
                    result_value = payload.get("repr")
            elif typ == "error" or "exception_message" in payload:
                msg = payload.get("exception_message", "Execution error")
                exc = RuntimeError(msg)
                if hasattr(exc, "add_note"):
                    try:
                        exc.add_note(f"Execution ID: {execution_id}")
                        tb = payload.get("traceback", "")
                        if tb:
                            exc.add_note(tb)
                    except Exception:
                        pass
                raise exc
            else:
                # Unknown dict; return as-is for diagnostics
                result_value = payload
        else:
            # Non-dict payload (e.g., plain string/int); return as-is
            result_value = payload

        # Fallback: ensure result_value is at least the raw payload when unset
        if result_value is None:
            result_value = payload

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
