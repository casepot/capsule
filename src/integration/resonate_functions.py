from __future__ import annotations

"""Resonate durable function registrations.

Provides a minimal durable_execute function wired for local mode using
AsyncExecutor via DI factory. The function follows generator-style
durable function semantics expected by the Resonate SDK.
"""

from typing import Any, Callable


def register_executor_functions(resonate: Any) -> Any:
    """Register durable executor-related functions with Resonate.

    Registers:
    - durable_execute v1.0.0
    """

    @resonate.register(name="durable_execute", version=1)  # type: ignore[misc]
    def durable_execute(ctx: Any, args: dict[str, Any]) -> Any:
        """
        Executes code durably via AsyncExecutor. Uses DI:
          - async_executor: created via factory (singleton=False)
          - namespace_manager: singleton
          - transport: provided in DI graph
        Applies pre/post checkpoints and proper timeouts per ctx.config.

        NOTE: ctx.lfc is synchronous in resonate-sdk 0.6.x and does not accept
        async callables. We therefore wrap AsyncExecutor.execute in a temporary
        synchronous shim that submits the coroutine to an event loop and
        blocks for the result. This is a transitional strategy ONLY.

        TODO(promise-first): Replace lfc usage with a promise-first flow:
          - promise = yield ctx.promise(id=...)
          - yield protocol_bridge.send_request(...)
          - result = yield promise
        This avoids loop-crossing hazards and aligns with the durable model.
        """
        code = args["code"]
        execution_id = args["execution_id"]

        # Pre-execution checkpoint (if available)
        if hasattr(ctx, "checkpoint"):
            yield ctx.checkpoint(
                "pre_execution",
                {"execution_id": execution_id, "code_len": len(code)},
            )

        # Resolve executor via factory from DI
        exec_factory: Callable[[Any], Any] = ctx.get_dependency("async_executor")
        executor = exec_factory(ctx)

        try:
            # Local run via a synchronous wrapper (ctx.lfc expects sync callable)
            # IMPORTANT: Do NOT create a new loop if the executor/transport already
            # owns a loop. In a full bridge-first design, this durable function will
            # not manage loops at all.
            def _run_executor_sync(_ctx: Any, a: dict[str, Any]) -> Any:
                import asyncio

                async def _inner() -> Any:
                    return await executor.execute(a["code"])

                # If a loop is running in this thread, we cannot run_until_complete.
                # In that case, submit to the executor's loop via run_coroutine_threadsafe.
                try:
                    running = asyncio.get_running_loop()
                except RuntimeError:
                    running = None

                if running is not None:
                    # TODO(loop-ownership): DI should expose the loop that owns the
                    # executor/transport; use it here to submit safely.
                    raise RuntimeError(
                        "lfc wrapper cannot run inside an active event loop; "
                        "switch to promise-first (ctx.promise + bridge) or provide a "
                        "threadsafe submit() facade bound to the executor's loop."
                    )

                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    return loop.run_until_complete(_inner())
                finally:
                    asyncio.set_event_loop(None)
                    loop.close()

            result = yield ctx.lfc(_run_executor_sync, {"code": code})
        except Exception as e:  # pragma: no cover - error path validated via notes
            # Add diagnostic context where supported
            if hasattr(e, "add_note"):
                e.add_note(f"Execution ID: {execution_id}")
                e.add_note(f"Code length: {len(code)}")
            raise
        finally:
            # Placeholder for optional namespace snapshot persistence
            pass

        # Post-execution checkpoint (if available)
        if hasattr(ctx, "checkpoint"):
            yield ctx.checkpoint("post_execution", {"execution_id": execution_id})

        return {"result": result, "execution_id": execution_id}

    # Expose handle for tests and local callers
    try:
        setattr(resonate, "capsule_durable_execute", durable_execute)
    except Exception:
        pass
    # Return the decorated function (supports .run() on real SDKs)
    return durable_execute
