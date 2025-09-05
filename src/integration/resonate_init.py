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


def initialize_resonate_local(transport: Any, resonate: Optional[Any] = None) -> Any:
    """Initialize Resonate in local mode with core dependencies wired.

    Args:
        transport: Bound MessageTransport instance
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
    resonate.set_dependency("transport", transport)

    # Protocol bridge
    bridge = ResonateProtocolBridge(resonate, transport)
    resonate.set_dependency("protocol_bridge", bridge)

    # Async executor factory (new instance per execution).
    resonate.set_dependency(
        "async_executor",
        lambda ctx: async_executor_factory(
            ctx=ctx,
            namespace_manager=namespace_manager,
            transport=transport,
            tla_timeout=getattr(getattr(ctx, "config", None), "tla_timeout", None),
        ),
    )

    # HITL input capability
    resonate.set_dependency(
        "input_capability",
        lambda: InputCapability(resonate, transport, bridge),
    )

    # NOTE(loop-ownership): The executor and transport own their event loop. Durable
    # functions must NOT create or manage loops. Prefer promise-first integration
    # (ctx.promise + protocol bridge) to avoid loop-spinning anti-patterns.

    return resonate

    # Note: no SDK fallback; tests must use the real 'resonate' package.
