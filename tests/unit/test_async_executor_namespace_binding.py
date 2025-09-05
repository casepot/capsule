"""Focused tests for AsyncExecutor globals binding and namespace persistence.

These tests ensure that functions defined under both the direct top-level
await path and the AST-fallback path bind their __globals__ to the live
session namespace mapping, and that global assignments persist across
executions via the merge-only policy.
"""

import asyncio
import builtins
import types

import pytest

from src.subprocess.async_executor import AsyncExecutor
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_tla_function_binds_live_globals():
    """Functions defined via direct TLA bind to the live globals dict.

    Verify that:
    - __globals__ of the function is the exact session namespace mapping
    - Updating a global in a later execution is observed by the function
    """
    ns = NamespaceManager()
    executor = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="tla-live-1")

    code_define = """
import asyncio
g = 1
async def addg(x):
    await asyncio.sleep(0)
    return x + g
_ = await asyncio.sleep(0)
"""
    await executor.execute(code_define)

    # Function should exist and bind __globals__ to the live mapping
    addg = ns.namespace.get("addg")
    assert isinstance(addg, types.FunctionType)
    assert addg.__globals__ is ns.namespace

    # Note: We do not assert that the function observes later updates here,
    # because on some Python versions the direct compile path for TLA may
    # fall back to the AST wrapper. That wrapper introduces closure binding
    # for names assigned in the same cell, which is addressed in Phase 1.


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_tla_global_assignment_inside_function_persists():
    """A function that assigns to a global should persist the change.

    Phase 1 resolution: Both direct TLA and AST fallback now preserve
    module-level globals. The wrapper hoists simple assigned names via
    'global' and merges global diffs after locals.
    """
    ns = NamespaceManager()
    executor = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="tla-live-2")

    code = """
import asyncio
g = 1
def setg(v):
    global g
    g = v
_ = await asyncio.sleep(0)
setg(7)
"""
    await executor.execute(code)

    assert ns.namespace.get("g") == 7


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ast_fallback_function_binds_live_globals(monkeypatch):
    """Force AST fallback and verify function __globals__ binds to live mapping."""
    ns = NamespaceManager()
    executor = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="tla-fallback-1")

    original_compile = builtins.compile

    call_count = {"n": 0}

    def fake_compile(source, filename, mode, flags=0, dont_inherit=False, optimize=-1):
        call_count["n"] += 1
        # Force the first call with TLA flags to fail to trigger fallback
        if flags & AsyncExecutor.PyCF_ALLOW_TOP_LEVEL_AWAIT and call_count["n"] == 1:
            raise SyntaxError("force ast fallback")
        return original_compile(source, filename, mode, flags=flags, dont_inherit=dont_inherit, optimize=optimize)

    # Patch compile in the async_executor module only
    import src.subprocess.async_executor as ae_mod
    monkeypatch.setattr(ae_mod, "compile", fake_compile, raising=False)

    code_define = """
import asyncio
g = 2
async def addg(x):
    await asyncio.sleep(0)
    return x + g
_ = await asyncio.sleep(0)
"""
    await executor.execute(code_define)

    addg = ns.namespace.get("addg")
    assert isinstance(addg, types.FunctionType)
    assert addg.__globals__ is ns.namespace

    # We do not assert observing later updates here because in the AST
    # fallback wrapper, names assigned in the same wrapper body become
    # closure-bound locals, not true globals. Phase 1 will address this.


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ast_fallback_function_sees_global_updates(monkeypatch):
    """Force AST fallback and verify that later global updates are observed.

    Phase 1 resolution: AST transform preserves module-level globals and
    functions bind __globals__ to the live mapping; later updates are observed.
    """
    ns = NamespaceManager()
    executor = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="tla-fallback-1b")

    original_compile = builtins.compile

    def fake_compile(source, filename, mode, flags=0, dont_inherit=False, optimize=-1):
        if flags & AsyncExecutor.PyCF_ALLOW_TOP_LEVEL_AWAIT:
            raise SyntaxError("force ast fallback")
        return original_compile(source, filename, mode, flags=flags, dont_inherit=dont_inherit, optimize=optimize)

    import src.subprocess.async_executor as ae_mod
    monkeypatch.setattr(ae_mod, "compile", fake_compile, raising=False)

    await executor.execute(
        """
import asyncio
g = 2
async def addg(x):
    await asyncio.sleep(0)
    return x + g
_ = await asyncio.sleep(0)
"""
    )

    await executor.execute(
        """
import asyncio
g = 8
z = await addg(12)
"""
    )

    assert ns.namespace.get("g") == 8
    assert ns.namespace.get("z") == 20


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ast_fallback_global_assignment_persists(monkeypatch):
    """Force AST fallback and verify global assignment inside function updates globals.

    Phase 1 resolution: AST fallback merge orders locals() first and global diffs
    after, ensuring module-level assignments persist.
    """
    ns = NamespaceManager()
    executor = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="tla-fallback-2")

    original_compile = builtins.compile
    first = {"done": False}

    def fake_compile(source, filename, mode, flags=0, dont_inherit=False, optimize=-1):
        # Fail only the first TLA compile to trigger fallback, pass through thereafter
        if not first["done"] and (flags & AsyncExecutor.PyCF_ALLOW_TOP_LEVEL_AWAIT):
            first["done"] = True
            raise SyntaxError("force ast fallback")
        return original_compile(source, filename, mode, flags=flags, dont_inherit=dont_inherit, optimize=optimize)

    import src.subprocess.async_executor as ae_mod
    monkeypatch.setattr(ae_mod, "compile", fake_compile, raising=False)

    code = """
import asyncio
g = 3
def setg(v):
    global g
    g = v
_ = await asyncio.sleep(0)
setg(11)
"""
    await executor.execute(code)

    assert ns.namespace.get("g") == 11
