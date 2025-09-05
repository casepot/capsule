"""Factory-based dependency injection helpers for AsyncExecutor.

Provides an awaitable promise adapter and a factory function to create
AsyncExecutor instances without temporal coupling.
"""

from __future__ import annotations

from typing import Optional
import asyncio

from ..subprocess.async_executor import AsyncExecutor
from ..subprocess.namespace import NamespaceManager


class AwaitablePromise:
    """Adapter to make promises awaitable in async contexts."""

    def __init__(self) -> None:
        self._future: Optional[asyncio.Future] = None

    def _ensure_future(self) -> asyncio.Future:
        if self._future is None:
            loop = asyncio.get_running_loop()
            self._future = loop.create_future()
        return self._future

    def set_result(self, value) -> None:
        fut = self._ensure_future()
        if not fut.done():
            fut.set_result(value)

    def set_exception(self, exc: BaseException) -> None:
        fut = self._ensure_future()
        if not fut.done():
            fut.set_exception(exc)

    def __await__(self):  # pragma: no cover - trivial delegation
        return self._ensure_future().__await__()


def async_executor_factory(
    ctx=None,
    namespace_manager: Optional[NamespaceManager] = None,
    transport=None,
    execution_id: Optional[str] = None,
    *,
    tla_timeout: Optional[float] = None,
) -> AsyncExecutor:
    """Factory returning ready-to-use AsyncExecutor instances.

    No initialize() needed - instances are fully configured on creation.

    Usage in DI:
        resonate.set_dependency(
            "async_executor",
            lambda ctx: async_executor_factory(ctx),
            singleton=False,
        )
    """
    ns = namespace_manager or NamespaceManager()
    exec_id = execution_id or getattr(ctx, "execution_id", "local-exec")
    # Allow ctx to carry default timeout if provided (e.g., ctx.config.tla_timeout)
    timeout = (
        tla_timeout
        if tla_timeout is not None
        else getattr(getattr(ctx, "config", None), "tla_timeout", 30.0)
    )
    # TODO(loop-ownership): Ensure the executor receives the loop that owns the
    # transport. The durable layer must not create or run event loops; if a sync
    # submit() facade is needed for ctx.lfc, implement it by posting to this loop
    # (e.g., run_coroutine_threadsafe) rather than creating a new one.
    return AsyncExecutor(
        namespace_manager=ns,
        transport=transport,
        execution_id=exec_id,
        tla_timeout=float(timeout),
    )
