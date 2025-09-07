"""Unit tests for AsyncExecutor AST fallback flags.

Covers gated behaviors:
- def→async def rewrite when function body contains await (flag ON)
- zero-arg lambda with await → async helper + assignment (flag ON)
- env var overrides for flags when constructor args left at defaults
"""

import asyncio
import os
import types
import pytest

from src.subprocess.async_executor import AsyncExecutor
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_def_await_rewrite_flag_enables_transform():
    ns = NamespaceManager()
    executor = AsyncExecutor(
        namespace_manager=ns,
        transport=None,
        execution_id="flags-def-1",
        enable_def_await_rewrite=True,
    )

    code = """
import asyncio
def add_one(x):
    return await asyncio.sleep(0, x + 1)
"""
    # Call fallback directly to exercise transform path
    await executor._execute_with_ast_transform(code)

    fn = ns.namespace.get("add_one")
    assert callable(fn)
    assert asyncio.iscoroutinefunction(fn)
    # Counter increments
    assert executor.stats.get("ast_transforms", 0) >= 1
    assert executor.stats.get("ast_transform_def_rewrites", 0) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lambda_helper_flag_enables_transform_and_callable():
    ns = NamespaceManager()
    executor = AsyncExecutor(
        namespace_manager=ns,
        transport=None,
        execution_id="flags-lam-1",
        enable_async_lambda_helper=True,
    )

    code = """
import asyncio
f = lambda: await asyncio.sleep(0, 'ok')
"""
    # Transform under fallback to define async helper and bind name
    await executor._execute_with_ast_transform(code)

    f = ns.namespace.get("f")
    assert callable(f)
    assert asyncio.iscoroutinefunction(f)

    # Now call it via native TLA path
    res = await executor.execute("result = await f()")
    assert ns.namespace.get("result") == "ok"
    # Counter increments
    assert executor.stats.get("ast_transforms", 0) >= 1
    assert executor.stats.get("ast_transform_lambda_helpers", 0) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_env_override_enables_def_rewrite(monkeypatch):
    ns = NamespaceManager()
    monkeypatch.setenv("ASYNC_EXECUTOR_ENABLE_DEF_AWAIT_REWRITE", "1")
    try:
        executor = AsyncExecutor(
            namespace_manager=ns,
            transport=None,
            execution_id="flags-env-def",
        )

        code = """
import asyncio
def g():
    return await asyncio.sleep(0, 5)
"""
        await executor._execute_with_ast_transform(code)
        g = ns.namespace.get("g")
        assert callable(g)
        assert asyncio.iscoroutinefunction(g)
        assert executor.stats.get("ast_transform_def_rewrites", 0) >= 1
    finally:
        monkeypatch.delenv("ASYNC_EXECUTOR_ENABLE_DEF_AWAIT_REWRITE", raising=False)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_env_override_enables_lambda_helper(monkeypatch):
    ns = NamespaceManager()
    monkeypatch.setenv("ASYNC_EXECUTOR_ENABLE_ASYNC_LAMBDA_HELPER", "true")
    try:
        executor = AsyncExecutor(
            namespace_manager=ns,
            transport=None,
            execution_id="flags-env-lam",
        )

        code = """
import asyncio
f = lambda: await asyncio.sleep(0, 9)
"""
        await executor._execute_with_ast_transform(code)
        f = ns.namespace.get("f")
        assert callable(f)
        assert asyncio.iscoroutinefunction(f)
        assert executor.stats.get("ast_transform_lambda_helpers", 0) >= 1
    finally:
        monkeypatch.delenv("ASYNC_EXECUTOR_ENABLE_ASYNC_LAMBDA_HELPER", raising=False)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_env_override_guard_does_not_apply_when_arg_provided(monkeypatch):
    # Set env to request rewrites, but pass explicit False to constructor
    monkeypatch.setenv("ASYNC_EXECUTOR_ENABLE_DEF_AWAIT_REWRITE", "1")
    monkeypatch.setenv("ASYNC_EXECUTOR_ENABLE_ASYNC_LAMBDA_HELPER", "1")

    try:
        ns = NamespaceManager()
        executor = AsyncExecutor(
            namespace_manager=ns,
            transport=None,
            execution_id="flags-guard-1",
            enable_def_await_rewrite=False,
            enable_async_lambda_helper=False,
        )

        # def with await should raise SyntaxError without def-rewrite transform
        code_def = """
import asyncio
def h():
    return await asyncio.sleep(0, 3)
"""
        with pytest.raises(SyntaxError):
            await executor._execute_with_ast_transform(code_def)
        assert executor.stats.get("ast_transform_def_rewrites", 0) == 0

        # lambda with await should raise SyntaxError without helper transform
        code_lam = """
import asyncio
f = lambda: await asyncio.sleep(0, 1)
"""
        with pytest.raises(SyntaxError):
            await executor._execute_with_ast_transform(code_lam)
        assert executor.stats.get("ast_transform_lambda_helpers", 0) == 0
    finally:
        monkeypatch.delenv("ASYNC_EXECUTOR_ENABLE_DEF_AWAIT_REWRITE", raising=False)
        monkeypatch.delenv("ASYNC_EXECUTOR_ENABLE_ASYNC_LAMBDA_HELPER", raising=False)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_def_rewrite_does_not_rewrite_outer_def_with_inner_async_def():
    """With def-rewrite enabled, do not rewrite an outer def if only an inner async def awaits.

    This guards against overmatching when scanning the subtree: the outer def should remain
    a normal function even if a nested async def contains await.
    """
    ns = NamespaceManager()
    executor = AsyncExecutor(
        namespace_manager=ns,
        transport=None,
        execution_id="flags-scope-1",
        enable_def_await_rewrite=True,
    )

    code = """
import asyncio
def outer():
    async def inner():
        await asyncio.sleep(0)
        return 1
    return 2
"""
    # This code is valid Python; fallback not strictly required, but exercise fallback path
    await executor._execute_with_ast_transform(code)

    outer = ns.namespace.get("outer")
    assert callable(outer)
    # Ensure not rewritten to coroutine function
    import asyncio as _asyncio
    assert not _asyncio.iscoroutinefunction(outer)
