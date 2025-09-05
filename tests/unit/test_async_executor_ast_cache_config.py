import os
import hashlib
import pytest

from src.subprocess.async_executor import AsyncExecutor
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
def test_constructor_sets_cache_size():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="cache1", ast_cache_max_size=2)
    codes = [f"x = {i}" for i in range(3)]
    hashes = [hashlib.md5(c.encode()).hexdigest() for c in codes]
    for c in codes:
        ex.analyze_execution_mode(c)
    assert len(ex._ast_cache) == 2
    assert hashes[0] not in ex._ast_cache
    assert hashes[1] in ex._ast_cache and hashes[2] in ex._ast_cache


@pytest.mark.unit
def test_env_override_for_cache_size(monkeypatch):
    monkeypatch.setenv("ASYNC_EXECUTOR_AST_CACHE_SIZE", "1")
    ns = NamespaceManager()
    # Do not override ast_cache_max_size explicitly (use default path)
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="cache2")
    # Add two entries; cache should keep only 1
    ex.analyze_execution_mode("a = 1")
    ex.analyze_execution_mode("b = 2")
    assert len(ex._ast_cache) == 1


@pytest.mark.unit
def test_disable_cache_with_none():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="cache3", ast_cache_max_size=None)
    ex.analyze_execution_mode("x = 1")
    ex.analyze_execution_mode("y = 2")
    # Cache disabled means internal cache remains empty
    assert len(ex._ast_cache) == 0

