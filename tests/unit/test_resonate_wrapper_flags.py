"""Factory flag threading tests for async_executor_factory.

Ensures ctx.config flags are threaded into AsyncExecutor constructor.
"""

import pytest
import linecache

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
def test_factory_threads_detection_flags_from_config():
    class Cfg:
        def __init__(self):
            self.enable_overshadow_guard = False
            self.require_import_for_module_calls = False

    class Ctx:
        def __init__(self):
            self.execution_id = "factory-detect-flags-config"
            self.config = Cfg()

    ns = NamespaceManager()
    ex = async_executor_factory(ctx=Ctx(), namespace_manager=ns, transport=None)

    assert getattr(ex, "_enable_overshadow_guard") is False
    assert getattr(ex, "_require_import_for_module_calls") is False


@pytest.mark.unit
def test_factory_param_overrides_detection_flags():
    class Cfg:
        def __init__(self):
            self.enable_overshadow_guard = True
            self.require_import_for_module_calls = True

    class Ctx:
        def __init__(self):
            self.execution_id = "factory-detect-flags-param"
            self.config = Cfg()

    ns = NamespaceManager()
    ex = async_executor_factory(
        ctx=Ctx(),
        namespace_manager=ns,
        transport=None,
        enable_overshadow_guard=False,
        require_import_for_module_calls=False,
    )

    assert getattr(ex, "_enable_overshadow_guard") is False
    assert getattr(ex, "_require_import_for_module_calls") is False


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_factory_threads_fallback_linecache_param():
    class Ctx:
        def __init__(self):
            self.execution_id = "factory-lc-param"
            self.config = type("cfg", (), {})()

    ctx = Ctx()
    ns = NamespaceManager()
    ex = async_executor_factory(ctx=ctx, namespace_manager=ns, transport=None, fallback_linecache_max_size=2)

    # Trigger 3 fallbacks and verify LRU eviction of the first
    def run(code: str):
        return ex._execute_with_ast_transform(code)

    fnames = []
    for i in range(3):
        code = f"a={i+1}\nb=0\nc=a/b\n"
        try:
            await run(code)
        except ZeroDivisionError as exc:
            tb = exc.__traceback__
            frames = []
            while tb is not None:
                frames.append((tb.tb_frame.f_code.co_filename, tb.tb_lineno))
                tb = tb.tb_next
            match = [f for f in frames if str(f[0]).startswith("<async_fallback")]
            assert match
            fnames.append(match[-1][0])

    assert len(fnames) == 3
    assert fnames[0] not in linecache.cache
    assert fnames[1] in linecache.cache and fnames[2] in linecache.cache


@pytest.mark.unit
@pytest.mark.asyncio
async def test_factory_threads_fallback_linecache_config():
    class Cfg:
        def __init__(self):
            self.fallback_linecache_max_size = 1

    class Ctx:
        def __init__(self):
            self.execution_id = "factory-lc-config"
            self.config = Cfg()

    ns = NamespaceManager()
    ex = async_executor_factory(ctx=Ctx(), namespace_manager=ns, transport=None)

    fnames = []
    for i in range(2):
        code = f"x={i}\ny=0\nz=x/y\n"
        try:
            await ex._execute_with_ast_transform(code)
        except ZeroDivisionError as exc:
            tb = exc.__traceback__
            frames = []
            while tb is not None:
                frames.append((tb.tb_frame.f_code.co_filename, tb.tb_lineno))
                tb = tb.tb_next
            match = [f for f in frames if str(f[0]).startswith("<async_fallback")]
            assert match
            fnames.append(match[-1][0])

    assert len(fnames) == 2
    assert fnames[0] not in linecache.cache
    assert fnames[1] in linecache.cache


@pytest.mark.unit
@pytest.mark.asyncio
async def test_factory_env_override_applies_when_param_and_config_absent(monkeypatch):
    monkeypatch.setenv("ASYNC_EXECUTOR_FALLBACK_LINECACHE_MAX", "3")
    try:
        class Ctx:
            def __init__(self):
                self.execution_id = "factory-lc-env"
                self.config = type("cfg", (), {})()

        ns = NamespaceManager()
        ex = async_executor_factory(ctx=Ctx(), namespace_manager=ns, transport=None)

        fnames = []
        for i in range(4):
            code = f"p={i}\nq=0\nr=p/q\n"
            try:
                await ex._execute_with_ast_transform(code)
            except ZeroDivisionError as exc:
                tb = exc.__traceback__
                frames = []
                while tb is not None:
                    frames.append((tb.tb_frame.f_code.co_filename, tb.tb_lineno))
                    tb = tb.tb_next
                match = [f for f in frames if str(f[0]).startswith("<async_fallback")]
                assert match
                fnames.append(match[-1][0])

        # With capacity 3, the first should be evicted; last three present
        assert fnames[0] not in linecache.cache
        for fn in fnames[1:]:
            assert fn in linecache.cache
    finally:
        monkeypatch.delenv("ASYNC_EXECUTOR_FALLBACK_LINECACHE_MAX", raising=False)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_factory_explicit_param_wins_over_env(monkeypatch):
    monkeypatch.setenv("ASYNC_EXECUTOR_FALLBACK_LINECACHE_MAX", "1")
    try:
        class Ctx:
            def __init__(self):
                self.execution_id = "factory-lc-param-wins"
                self.config = type("cfg", (), {})()

        ns = NamespaceManager()
        ex = async_executor_factory(ctx=Ctx(), namespace_manager=ns, transport=None, fallback_linecache_max_size=2)

        fnames = []
        for i in range(3):
            code = f"m={i}\nn=0\no=m/n\n"
            try:
                await ex._execute_with_ast_transform(code)
            except ZeroDivisionError as exc:
                tb = exc.__traceback__
                frames = []
                while tb is not None:
                    frames.append((tb.tb_frame.f_code.co_filename, tb.tb_lineno))
                    tb = tb.tb_next
                match = [f for f in frames if str(f[0]).startswith("<async_fallback")]
                assert match
                fnames.append(match[-1][0])

        # Capacity 2 behavior: first evicted; last two present
        assert fnames[0] not in linecache.cache
        assert fnames[1] in linecache.cache and fnames[2] in linecache.cache
    finally:
        monkeypatch.delenv("ASYNC_EXECUTOR_FALLBACK_LINECACHE_MAX", raising=False)
