"""Factory flag threading tests for async_executor_factory.

Ensures ctx.config flags are threaded into AsyncExecutor constructor.
"""

import pytest

from src.integration.resonate_wrapper import async_executor_factory
from src.subprocess.namespace import NamespaceManager


class Cfg:
    def __init__(self):
        self.tla_timeout = 12.5
        self.enable_def_await_rewrite = True
        self.enable_async_lambda_helper = True


class Ctx:
    def __init__(self):
        self.execution_id = "factory-flags-1"
        self.config = Cfg()


@pytest.mark.unit
def test_factory_threads_transform_flags():
    ctx = Ctx()
    ns = NamespaceManager()

    executor = async_executor_factory(ctx=ctx, namespace_manager=ns, transport=None)

    # Flags should be threaded from ctx.config
    assert getattr(executor, "_enable_def_await_rewrite", False) is True
    assert getattr(executor, "_enable_async_lambda_helper", False) is True
    # Timeout also threaded
    assert executor.tla_timeout == pytest.approx(12.5)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_factory_flags_trigger_fallback_and_counters(monkeypatch):
    class Cfg2:
        def __init__(self):
            self.enable_def_await_rewrite = True
            self.enable_async_lambda_helper = True

    class Ctx2:
        def __init__(self):
            self.execution_id = "factory-flags-2"
            self.config = Cfg2()

    # Force TLA compile paths to fail to invoke fallback
    import builtins as _builtins
    original_compile = _builtins.compile

    def fake_compile(source, filename, mode, flags=0, dont_inherit=False, optimize=-1):
        from src.subprocess.async_executor import AsyncExecutor as _AE
        if flags & _AE.PyCF_ALLOW_TOP_LEVEL_AWAIT:
            raise SyntaxError("force fallback")
        return original_compile(source, filename, mode, flags=flags, dont_inherit=dont_inherit, optimize=optimize)

    import src.subprocess.async_executor as ae_mod
    monkeypatch.setattr(ae_mod, "compile", fake_compile, raising=False)

    ctx = Ctx2()
    ns = NamespaceManager()
    executor = async_executor_factory(ctx=ctx, namespace_manager=ns, transport=None)

    code = """
import asyncio
def f(x):
    return await asyncio.sleep(0, x + 1)
g = lambda: await asyncio.sleep(0, 'ok')
_ = await asyncio.sleep(0)
"""
    await executor.execute(code)

    # Both transforms should have occurred under fallback
    assert executor.stats.get("ast_transform_def_rewrites", 0) >= 1
    assert executor.stats.get("ast_transform_lambda_helpers", 0) >= 1

    import asyncio as _asyncio
    assert _asyncio.iscoroutinefunction(ns.namespace.get("f"))
    assert _asyncio.iscoroutinefunction(ns.namespace.get("g"))
