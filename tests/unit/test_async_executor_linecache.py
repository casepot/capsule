"""Tests for per-execution fallback filenames and linecache lifecycle.

These tests focus on:
- Unique virtual filenames per fallback
- LRU eviction when capacity is small
- Cleanup on executor.close()
"""

import pytest

from src.subprocess.async_executor import AsyncExecutor
from src.subprocess.namespace import NamespaceManager
import linecache


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fallback_uses_unique_filenames():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="linecache-uniq")

    code1 = "a=1\nb=0\nc=a/b\n"  # ZeroDivisionError at line 3
    code2 = "x=1\ny=0\nz=x/y\n"  # ZeroDivisionError at line 3 (different text)

    fnames = []
    for code in (code1, code2):
        try:
            await ex._execute_with_ast_transform(code)
        except ZeroDivisionError as exc:
            tb = exc.__traceback__
            frames = []
            while tb is not None:
                frames.append((tb.tb_frame.f_code.co_filename, tb.tb_lineno))
                tb = tb.tb_next
            # Find frame from our fallback filename prefix
            match = [f for f in frames if str(f[0]).startswith("<async_fallback")]
            assert match, f"No fallback frame found: {frames}"
            fnames.append(match[-1][0])

    assert len(fnames) == 2
    assert fnames[0] != fnames[1]
    assert all(str(fn).startswith("<async_fallback") for fn in fnames)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fallback_linecache_lru_eviction():
    ns = NamespaceManager()
    # Capacity 2, we'll register 3 fallbacks
    ex = AsyncExecutor(
        namespace_manager=ns,
        transport=None,
        execution_id="linecache-lru",
        fallback_linecache_max_size=2,
    )

    seen = []
    # generate 3 distinct codes that error to get frames/filenames
    for i in range(3):
        code = f"a={i+1}\nb=0\nc=a/b\n"
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
            seen.append(match[-1][0])

    assert len(seen) == 3
    # With capacity 2, the first should have been evicted from linecache
    first = seen[0]
    last_two = seen[1:]
    assert all(str(fn).startswith("<async_fallback") for fn in last_two)
    assert first not in linecache.cache
    for fn in last_two:
        assert fn in linecache.cache


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fallback_linecache_cleanup_on_close():
    ns = NamespaceManager()
    ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="linecache-close", fallback_linecache_max_size=None)

    code = "a=1\nb=0\nc=a/b\n"
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
        fname = match[-1][0]
        # Ensure present before close
        assert fname in linecache.cache

    await ex.close()
    # After close, entry should be removed
    assert fname not in linecache.cache

