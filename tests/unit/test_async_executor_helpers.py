"""Unit tests for internal helper methods of AsyncExecutor.

These tests validate behavior in isolation without going through the full
fallback execution path, keeping scope minimal and focused.
"""

import ast
import asyncio
import linecache
import types

import pytest

from src.subprocess.async_executor import AsyncExecutor
from src.subprocess.namespace import NamespaceManager


def _mk_module_from_code(code: str, filename: str = "<x>") -> ast.Module:
    return ast.parse(code, filename=filename, type_comments=True)


@pytest.mark.unit
def test_apply_gated_transforms_flags_off():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="helpers-off")

    code = """
def f():
    return await g()

h = lambda: await g()
"""
    tree = _mk_module_from_code(code)
    body = ex._apply_gated_transforms(tree)
    # No transforms applied by default
    assert isinstance(body[0], ast.FunctionDef)
    assert isinstance(body[1], ast.Assign)


@pytest.mark.unit
def test_apply_gated_transforms_def_rewrite_on():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="helpers-def", enable_def_await_rewrite=True)

    code = """
def f():
    return await g()
"""
    tree = _mk_module_from_code(code)
    body = ex._apply_gated_transforms(tree)
    assert isinstance(body[0], ast.AsyncFunctionDef)
    assert ex.stats.get("ast_transform_def_rewrites", 0) >= 1


@pytest.mark.unit
def test_apply_gated_transforms_lambda_helper_on():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="helpers-lam", enable_async_lambda_helper=True)

    code = """
f = lambda: await g()
"""
    tree = _mk_module_from_code(code)
    body = ex._apply_gated_transforms(tree)
    # Should expand to two statements: async helper def + assign
    assert len(body) == 2
    assert isinstance(body[0], ast.AsyncFunctionDef)
    assert isinstance(body[1], ast.Assign)
    assert ex.stats.get("ast_transform_lambda_helpers", 0) >= 1


@pytest.mark.unit
def test_build_wrapper_body_expression():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="helpers-body-expr")

    tree = _mk_module_from_code("1 + 2")
    body, is_expr = ex._build_wrapper_body(tree)
    assert is_expr is True
    assert len(body) == 1 and isinstance(body[0], ast.Return)
    ret = body[0]
    # The Return should have source location copied from the expression
    assert hasattr(ret, "lineno") and hasattr(ret, "col_offset")


@pytest.mark.unit
def test_build_wrapper_body_statements():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="helpers-body-stmt")

    tree = _mk_module_from_code("a=1\nb=2\n")
    body, is_expr = ex._build_wrapper_body(tree)
    assert is_expr is False
    # Original statements plus trailing Return(locals())
    assert len(body) == 3
    assert isinstance(body[-1], ast.Return)


@pytest.mark.unit
def test_compile_and_register_linecache():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="helpers-compile", fallback_linecache_max_size=16)

    # Build a minimal module with our expected wrapper name
    async_def = ast.AsyncFunctionDef(
        name="__async_exec__",
        args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=[ast.Return(value=ast.Constant(value=1))],
        decorator_list=[],
        returns=None,
        lineno=1,
        col_offset=0,
    )
    module = ast.Module(body=[async_def], type_ignores=[])
    filename = "<async_fallback:test:deadbeef:1>"
    code = "return 1"

    compiled = ex._compile_and_register(code, module, filename)
    assert isinstance(compiled, types.CodeType)
    assert filename in linecache.cache

    # Cleanup via close() (run the coroutine directly on current loop)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(ex.close())
    assert filename not in linecache.cache


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_wrapper_and_merge_expression():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="helpers-run-expr")

    async def coro():
        return "ok"

    global_ns = ns.namespace
    pre = dict(global_ns)
    result = await ex._run_wrapper_and_merge(coro, global_ns, pre, True, "expr")
    assert result == "ok"
    assert ns.namespace.get("_") == "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_wrapper_and_merge_statements():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="helpers-run-stmt")

    async def coro():
        # Simulate locals() return with some protected keys
        return {"x": 5, "__builtins__": {}, "asyncio": object(), "__async_exec__": object()}

    global_ns = ns.namespace
    pre = dict(global_ns)
    result = await ex._run_wrapper_and_merge(coro, global_ns, pre, False, "stmt")
    assert result is None
    assert ns.namespace.get("x") == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_wrapper_and_merge_statements_non_dict_warns(monkeypatch):
    """Wrapper returns non-dict for statements: warn and do not mutate namespace."""
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="helpers-run-warn")

    async def coro():
        return 123  # non-dict should trigger warning path

    # Capture warning call
    calls = []
    from src.subprocess import async_executor as ae_mod

    def fake_warning(msg, **kw):
        calls.append((msg, kw))

    monkeypatch.setattr(ae_mod.logger, "warning", fake_warning, raising=True)

    global_ns = ns.namespace
    pre = dict(global_ns)
    result = await ex._run_wrapper_and_merge(coro, global_ns, pre, False, "stmt")
    assert result == 123
    # Namespace should be unchanged (no new user keys)
    new_keys = set(global_ns.keys()) - set(pre.keys())
    # Allow engine internals that may be present; we only assert no user key 'x'
    assert "x" not in new_keys
    # Warning should have been recorded
    assert calls, "Expected a warning for non-dict locals() result"
