from __future__ import annotations

"""Local-mode Resonate initialization and DI wiring.

This provides a minimal local initializer to wire AsyncExecutor, protocol
bridge, and HITL input capability using the in-repo DI factory. This module
REQUIRES the real Resonate SDK (no stub fallback).
"""

from typing import Any, Optional

from .resonate_functions import register_executor_functions
from .resonate_bridge import ResonateProtocolBridge
from .capability_input import InputCapability
from .resonate_wrapper import async_executor_factory
from ..subprocess.namespace import NamespaceManager
from ..protocol.messages import InputResponseMessage, ResultMessage, ErrorMessage
import structlog

logger = structlog.get_logger()


def initialize_resonate_local(session: Any, resonate: Optional[Any] = None) -> Any:
    """Initialize Resonate in local mode with core dependencies wired.

    Args:
        session: Session instance (transport owner and single reader)
        resonate: Optional pre-created Resonate-like object; if None, attempts
                  to create a local instance (or stub) for development.

    Returns:
        Resonate-like instance with functions and dependencies registered.
    """
    if resonate is None:
        from resonate import Resonate

        resonate = Resonate.local()

    # Register durable functions
    register_executor_functions(resonate)

    # Core singletons
    namespace_manager = NamespaceManager()
    resonate.set_dependency("namespace_manager", namespace_manager)
    resonate.set_dependency("session", session)

    # Protocol bridge
    bridge = ResonateProtocolBridge(resonate, session)
    resonate.set_dependency("protocol_bridge", bridge)

    # Async executor factory (new instance per execution).
    def _exec_factory(ctx: Any) -> Any:
        timeout = getattr(getattr(ctx, "config", None), "tla_timeout", None)
        return async_executor_factory(
            ctx=ctx,
            namespace_manager=namespace_manager,
            transport=None,  # AsyncExecutor skeleton not used in promise-first path
            tla_timeout=timeout,
        )

    resonate.set_dependency("async_executor", _exec_factory)

    # HITL input capability
    resonate.set_dependency(
        "input_capability",
        lambda: InputCapability(resonate, bridge),
    )

    # NOTE(loop-ownership): The executor and transport own their event loop. Durable
    # functions must NOT create or manage loops. Prefer promise-first integration
    # (ctx.promise + protocol bridge) to avoid loop-spinning anti-patterns.

    # Register message interceptor on the session to route responses to the bridge
    def _interceptor(message: Any) -> None:
        if isinstance(message, (InputResponseMessage, ResultMessage, ErrorMessage)):
            try:
                # Schedule async route to remain non-blocking
                import asyncio as _asyncio
                task = _asyncio.create_task(bridge.route_response(message))  # type: ignore[arg-type]
                def _done(t: _asyncio.Task):
                    if t.cancelled():
                        return
                    exc = t.exception()
                    if exc:
                        logger.debug(
                            "bridge_route_response_task_error",
                            error=str(exc),
                            message_type=getattr(message, "type", None),
                        )
                task.add_done_callback(_done)
            except Exception:
                # Never raise from interceptor
                return

    if hasattr(session, "add_message_interceptor"):
        session.add_message_interceptor(_interceptor)

    return resonate

    # Note: no SDK fallback; tests must use the real 'resonate' package.
