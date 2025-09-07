"""Factory-based dependency injection helpers for AsyncExecutor.

Provides an awaitable promise adapter and a factory function to create
AsyncExecutor instances without temporal coupling.
"""

from __future__ import annotations

from typing import Optional, Any
import asyncio

from ..subprocess.async_executor import AsyncExecutor
from ..protocol.transport import MessageTransport
from ..subprocess.namespace import NamespaceManager


class AwaitablePromise:
    """Adapter to make promises awaitable in async contexts."""

    def __init__(self) -> None:
        self._future: Optional[asyncio.Future[Any]] = None

    def _ensure_future(self) -> asyncio.Future[Any]:
        if self._future is None:
            loop = asyncio.get_running_loop()
            self._future = loop.create_future()
        return self._future

    def set_result(self, value: Any) -> None:
        fut = self._ensure_future()
        if not fut.done():
            fut.set_result(value)

    def set_exception(self, exc: BaseException) -> None:
        fut = self._ensure_future()
        if not fut.done():
            fut.set_exception(exc)

    def __await__(self) -> Any:  # pragma: no cover - trivial delegation
        return self._ensure_future().__await__()


def async_executor_factory(
    ctx: Any | None = None,
    namespace_manager: Optional[NamespaceManager] = None,
    transport: MessageTransport | None = None,
    execution_id: Optional[str] = None,
    *,
    tla_timeout: Optional[float] = None,
    ast_cache_max_size: int | None = None,
    blocking_modules: set[str] | None = None,
    blocking_methods_by_module: dict[str, set[str]] | None = None,
    warn_on_blocking: bool | None = None,
    enable_def_await_rewrite: bool | None = None,
    enable_async_lambda_helper: bool | None = None,
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
    eid = execution_id if execution_id is not None else getattr(ctx, "execution_id", "local-exec")
    exec_id: str = eid if isinstance(eid, str) else "local-exec"
    # Allow ctx to carry default timeout if provided (e.g., ctx.config.tla_timeout)
    timeout = (
        tla_timeout
        if tla_timeout is not None
        else getattr(getattr(ctx, "config", None), "tla_timeout", 30.0)
    )
    # Config overrides for detection and cache size, if present on ctx.config
    cfg = getattr(ctx, "config", None)
    if ast_cache_max_size is None and cfg is not None:
        ast_cache_max_size = getattr(cfg, "ast_cache_max_size", None)
    if blocking_modules is None and cfg is not None:
        blocking_modules = getattr(cfg, "blocking_modules", None)
    if blocking_methods_by_module is None and cfg is not None:
        blocking_methods_by_module = getattr(cfg, "blocking_methods_by_module", None)
    if warn_on_blocking is None and cfg is not None:
        warn_on_blocking = getattr(cfg, "warn_on_blocking", True)
    # New flags for AST fallback policy (default OFF)
    if enable_def_await_rewrite is None and cfg is not None:
        if hasattr(cfg, "enable_def_await_rewrite"):
            enable_def_await_rewrite = bool(getattr(cfg, "enable_def_await_rewrite"))
    if enable_async_lambda_helper is None and cfg is not None:
        if hasattr(cfg, "enable_async_lambda_helper"):
            enable_async_lambda_helper = bool(getattr(cfg, "enable_async_lambda_helper"))
    # TODO(loop-ownership): Ensure the executor receives the loop that owns the
    # transport. The durable layer must not create or run event loops; if a sync
    # submit() facade is needed for ctx.lfc, implement it by posting to this loop
    # (e.g., run_coroutine_threadsafe) rather than creating a new one.
    return AsyncExecutor(
        namespace_manager=ns,
        transport=transport,
        execution_id=exec_id,
        tla_timeout=float(timeout),
        ast_cache_max_size=ast_cache_max_size if ast_cache_max_size is not None else 100,
        blocking_modules=blocking_modules,
        blocking_methods_by_module=blocking_methods_by_module,
        warn_on_blocking=True if warn_on_blocking is None else bool(warn_on_blocking),
        enable_def_await_rewrite=enable_def_await_rewrite,
        enable_async_lambda_helper=enable_async_lambda_helper,
    )
