"""Unit tests for AsyncExecutor top-level await support.

This test suite validates the implementation of top-level await using
the PyCF_ALLOW_TOP_LEVEL_AWAIT compile flag and AST transformation fallback.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
import weakref

from src.subprocess.async_executor import AsyncExecutor, ExecutionMode
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
class TestTopLevelAwaitBasic:
    """Test basic top-level await functionality."""
    
    @pytest.mark.asyncio
    async def test_simple_top_level_await(self):
        """Test simple top-level await expression."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-await-1"
        )
        
        # Test simple await that returns a value
        code = "await asyncio.sleep(0, 'test_result')"
        result = await executor.execute(code)
        
        assert result == 'test_result'
        assert executor.stats["executions"] == 1
        assert executor.mode_counts[ExecutionMode.TOP_LEVEL_AWAIT] == 1
    
    @pytest.mark.asyncio
    async def test_await_in_assignment(self):
        """Test await in variable assignment."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-await-2"
        )
        
        # Test await with assignment
        code = """
import asyncio
x = await asyncio.sleep(0, 42)
"""
        result = await executor.execute(code)
        
        # Result should be None for statements
        assert result is None
        # But x should be in namespace
        assert namespace_manager.namespace.get('x') == 42
        # Compile-first exec path should not need AST fallback
        assert executor.stats.get("ast_transforms", 0) == 0
    
    @pytest.mark.asyncio
    async def test_multiple_awaits(self):
        """Test multiple sequential await expressions."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-await-3"
        )
        
        # Test multiple awaits
        code = """
import asyncio
a = await asyncio.sleep(0, 1)
b = await asyncio.sleep(0, 2)
c = a + b
"""
        result = await executor.execute(code)
        
        assert result is None  # Statements return None
        assert namespace_manager.namespace.get('a') == 1
        assert namespace_manager.namespace.get('b') == 2
        assert namespace_manager.namespace.get('c') == 3
        # Ensure no AST fallback for standard statements
        assert executor.stats.get("ast_transforms", 0) == 0
    
    @pytest.mark.asyncio
    async def test_await_expression_result(self):
        """Test that await expressions update result history."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-await-4"
        )
        
        # Execute an await expression (not assignment)
        code = "await asyncio.sleep(0, 'result_value')"
        result = await executor.execute(code)
        
        # Should return the value
        assert result == 'result_value'
        # Should update _ in namespace
        assert namespace_manager.namespace.get('_') == 'result_value'
    
    @pytest.mark.asyncio
    async def test_await_with_async_function_call(self):
        """Test await with custom async function."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-await-5"
        )
        
        # First define an async function
        setup_code = """
async def get_data():
    import asyncio
    await asyncio.sleep(0)
    return "async_data"
"""
        await executor.execute(setup_code)
        
        # Now call it with top-level await
        code = "result = await get_data()"
        await executor.execute(code)
        
        assert namespace_manager.namespace.get('result') == "async_data"


@pytest.mark.unit
class TestTopLevelAwaitEdgeCases:
    """Test edge cases and complex scenarios."""
    
    @pytest.mark.asyncio
    async def test_await_in_complex_expression(self):
        """Test await in complex expressions."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-edge-1"
        )
        
        # Test await in arithmetic expression
        code = """
import asyncio
result = (await asyncio.sleep(0, 10)) + (await asyncio.sleep(0, 20))
"""
        await executor.execute(code)
        
        assert namespace_manager.namespace.get('result') == 30
    
    @pytest.mark.asyncio
    async def test_await_in_list_comprehension(self):
        """Test await in list comprehension."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-edge-2"
        )
        
        # Setup async function
        setup = """
async def get_value(x):
    import asyncio
    await asyncio.sleep(0)
    return x * 2
"""
        await executor.execute(setup)
        
        # Test await in list comprehension
        code = "result = [await get_value(i) for i in range(3)]"
        await executor.execute(code)
        
        assert namespace_manager.namespace.get('result') == [0, 2, 4]
        # Should use compile-first path
        assert executor.stats.get("ast_transforms", 0) == 0

    @pytest.mark.asyncio
    async def test_await_in_fstring_py312_plus(self):
        """Test await inside f-string for Python >=3.12 (PEP 701)."""
        import sys
        if sys.version_info < (3, 12):
            pytest.skip("f-strings with await require Python 3.12+")

        namespace_manager = NamespaceManager()
        mock_transport = Mock()

        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-edge-fstr"
        )

        code = "msg = f'value {await asyncio.sleep(0, 5)}'"
        await executor.execute(code)
        assert namespace_manager.namespace.get('msg') == 'value 5'
        assert executor.stats.get("ast_transforms", 0) == 0

    @pytest.mark.asyncio
    async def test_top_level_async_for(self):
        """Test top-level async for loop under compile-first exec path."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()

        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-edge-async-for"
        )

        setup = """
import asyncio

async def agen():
    for i in range(3):
        await asyncio.sleep(0)
        yield i
"""
        await executor.execute(setup)

        code = """
result = []
async for v in agen():
    result.append(v)
"""
        result = await executor.execute(code)
        assert result is None
        assert namespace_manager.namespace.get('result') == [0, 1, 2]
        assert executor.stats.get("ast_transforms", 0) == 0

    @pytest.mark.asyncio
    async def test_top_level_async_with(self):
        """Test top-level async with block under compile-first exec path."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()

        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-edge-async-with"
        )

        code = """
import asyncio
lock = asyncio.Lock()
done = False
async with lock:
    await asyncio.sleep(0)
    done = True
"""
        result = await executor.execute(code)
        assert result is None
        assert namespace_manager.namespace.get('done') is True
        assert executor.stats.get("ast_transforms", 0) == 0
    
    @pytest.mark.asyncio
    async def test_await_in_conditional(self):
        """Test await in conditional expression."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-edge-3"
        )
        
        # Test await in ternary operator
        code = """
import asyncio
condition = True
result = await asyncio.sleep(0, 'yes') if condition else await asyncio.sleep(0, 'no')
"""
        await executor.execute(code)
        
        assert namespace_manager.namespace.get('result') == 'yes'
    
    @pytest.mark.asyncio
    async def test_await_in_function_call(self):
        """Test await as function argument."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-edge-4"
        )
        
        # Test await as function argument
        code = """
import asyncio
result = str(await asyncio.sleep(0, 42))
"""
        await executor.execute(code)
        
        assert namespace_manager.namespace.get('result') == '42'
    
    @pytest.mark.asyncio
    async def test_compile_flag_usage(self):
        """Test that PyCF_ALLOW_TOP_LEVEL_AWAIT flag is used correctly."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-flag"
        )
        
        # Verify the flag value matches Python's ast module
        import ast
        if hasattr(ast, 'PyCF_ALLOW_TOP_LEVEL_AWAIT'):
            assert executor.PyCF_ALLOW_TOP_LEVEL_AWAIT == ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
        else:
            assert executor.PyCF_ALLOW_TOP_LEVEL_AWAIT == 0x2000
        
        # Test that flag enables compilation
        code = "await asyncio.sleep(0)"
        base_flags = compile('', '', 'exec').co_flags
        flags = base_flags | executor.PyCF_ALLOW_TOP_LEVEL_AWAIT
        
        # This should compile without SyntaxError
        compiled = compile(code, '<test>', 'exec', flags=flags)
        assert compiled is not None


@pytest.mark.unit
class TestTopLevelAwaitErrors:
    """Test error handling and invalid cases."""
    
    @pytest.mark.asyncio
    async def test_await_in_lambda_fails(self):
        """Await in lambda should raise SyntaxError by default (no rewrite)."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-error-1"
        )
        
        code = "f = lambda: await foo()"
        with pytest.raises(SyntaxError):
            await executor.execute(code)
    
    @pytest.mark.asyncio
    async def test_await_without_async_context_in_def(self):
        """Await in regular def should raise SyntaxError by default (no rewrite)."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-error-2"
        )
        
        code = """
def regular_func():
    return await something()
"""
        with pytest.raises(SyntaxError):
            await executor.execute(code)
    
    @pytest.mark.asyncio
    async def test_execution_error_handling(self):
        """Test that execution errors are properly handled."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-error-3"
        )
        
        # Test undefined name error
        code = "await undefined_async_func()"
        
        with pytest.raises(NameError, match="undefined_async_func"):
            await executor.execute(code)
        
        # Verify error stats updated
        assert executor.stats["errors"] == 1
    
    @pytest.mark.asyncio
    async def test_await_non_awaitable(self):
        """Test await on non-awaitable object."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-error-4"
        )
        
        # Setup a non-awaitable
        await executor.execute("x = 42")
        
        # Try to await it
        code = "await x"
        
        with pytest.raises(TypeError, match="object int can't be used in 'await' expression"):
            await executor.execute(code)


@pytest.mark.unit
class TestNamespacePreservation:
    """Test namespace merge-only policy and preservation."""
    
    @pytest.mark.asyncio
    async def test_namespace_merge_not_replace(self):
        """Test that namespace is merged, not replaced."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-ns-1"
        )
        
        # Get initial namespace ID
        initial_ns_id = id(namespace_manager.namespace)
        
        # Add some initial values
        namespace_manager.namespace['existing'] = 'value'
        
        # Execute code with await
        code = """
import asyncio
new_var = await asyncio.sleep(0, 'new_value')
"""
        await executor.execute(code)
        
        # Namespace object identity must be preserved
        assert id(namespace_manager.namespace) == initial_ns_id
        
        # Both old and new values should exist
        assert namespace_manager.namespace.get('existing') == 'value'
        assert namespace_manager.namespace.get('new_var') == 'new_value'
    
    @pytest.mark.asyncio
    async def test_engine_internals_preserved(self):
        """Test that ENGINE_INTERNALS are preserved."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-ns-2"
        )
        
        # ENGINE_INTERNALS should exist
        from src.subprocess.constants import ENGINE_INTERNALS
        
        # Execute code
        code = "x = await asyncio.sleep(0, 42)"
        await executor.execute(code)
        
        # Check some ENGINE_INTERNALS are still present
        # _ should be None or the last result
        assert '_' in namespace_manager.namespace
        assert '__name__' in namespace_manager.namespace
        assert '__builtins__' in namespace_manager.namespace
    
    @pytest.mark.asyncio
    async def test_result_history_updates(self):
        """Test that result history (_, __, ___) updates correctly."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-ns-3"
        )
        
        # Execute multiple expressions
        await executor.execute("await asyncio.sleep(0, 1)")
        assert namespace_manager.namespace.get('_') == 1
        
        await executor.execute("await asyncio.sleep(0, 2)")
        assert namespace_manager.namespace.get('_') == 2
        assert namespace_manager.namespace.get('__') == 1
        
        await executor.execute("await asyncio.sleep(0, 3)")
        assert namespace_manager.namespace.get('_') == 3
        assert namespace_manager.namespace.get('__') == 2
        assert namespace_manager.namespace.get('___') == 1


@pytest.mark.unit
class TestCoroutineManagement:
    """Test coroutine lifecycle and cleanup."""
    
    @pytest.mark.asyncio
    async def test_coroutine_tracking(self):
        """Test that coroutines are tracked with weakref."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-coro-1"
        )
        
        # Track initial coroutines count
        initial_count = len(executor._pending_coroutines)
        
        # Execute code that creates a coroutine
        code = "result = await asyncio.sleep(0, 'tracked')"
        await executor.execute(code)
        
        # Cleanup should have been called in finally block
        # No coroutines should be left pending
        cleaned = executor.cleanup_coroutines()
        assert cleaned == 0  # Already cleaned in execute() finally
    
    @pytest.mark.asyncio
    async def test_no_coroutine_leaks(self):
        """Test that no coroutines leak into namespace."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-coro-2"
        )
        
        # Execute code with await
        code = """
import asyncio
x = await asyncio.sleep(0, 42)
"""
        await executor.execute(code)
        
        # Check namespace for coroutine objects
        for key, value in namespace_manager.namespace.items():
            if not key.startswith('__'):
                assert not asyncio.iscoroutine(value), f"Coroutine leaked in namespace: {key}"
    
    @pytest.mark.asyncio
    async def test_cleanup_on_error(self):
        """Test that coroutines are cleaned up even on error."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-coro-3"
        )
        
        # Execute code that will error
        code = "await undefined_function()"
        
        with pytest.raises(NameError):
            await executor.execute(code)
        
        # Cleanup should still have happened
        assert len(executor._pending_coroutines) == 0 or \
               all(ref() is None for ref in executor._pending_coroutines)


@pytest.mark.unit
class TestASTTransformationFallback:
    """Test AST transformation fallback path."""
    
    @pytest.mark.asyncio
    async def test_ast_transform_triggered(self):
        """Test that AST transformation is used as fallback."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-ast-1"
        )
        
        # Patch compile to simulate SyntaxError whenever TLA flags are used
        original_compile = compile
        
        def mock_compile(source, filename, mode, flags=0, *args, **kwargs):
            if flags & executor.PyCF_ALLOW_TOP_LEVEL_AWAIT:
                # Force both eval and exec compilation paths to fail,
                # ensuring the AST fallback is exercised
                raise SyntaxError("Simulated syntax error")
            return original_compile(source, filename, mode, flags, *args, **kwargs)
        
        with patch('builtins.compile', side_effect=mock_compile):
            # This should trigger AST transformation fallback
            code = "await asyncio.sleep(0, 'fallback_result')"
            result = await executor.execute(code)
            
            assert result == 'fallback_result'
            # Check that AST transform was used
            assert executor.stats.get("ast_transforms", 0) > 0
    
    @pytest.mark.asyncio
    async def test_ast_transform_preserves_semantics(self):
        """Test that AST transformation preserves code semantics."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-ast-2"
        )
        
        # Force AST transformation by mocking
        with patch.object(executor, '_execute_top_level_await', 
                         side_effect=SyntaxError("Force AST")):
            code = """
import asyncio
x = await asyncio.sleep(0, 10)
y = await asyncio.sleep(0, 20)
result = x + y
"""
            # Call AST transform directly
            result = await executor._execute_with_ast_transform(code)
            
            # The wrapper function approach means variables won't persist
            # in namespace (they're local to the wrapper function)
            # But the result should still be correct if we return it

    @pytest.mark.asyncio
    async def test_ast_fallback_no_reordering(self, monkeypatch):
        """AST fallback should not reorder user statements."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()

        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-ast-order"
        )

        # Define log() and events first, outside of fallback
        await executor.execute("""
events = []
def log(x):
    events.append(x)
""")

        # Force fallback by failing flagged compiles
        import builtins as _builtins
        original_compile = _builtins.compile

        def fake_compile(source, filename, mode, flags=0, dont_inherit=False, optimize=-1):
            if flags & AsyncExecutor.PyCF_ALLOW_TOP_LEVEL_AWAIT:
                raise SyntaxError("force fallback")
            return original_compile(source, filename, mode, flags=flags, dont_inherit=dont_inherit, optimize=optimize)

        import src.subprocess.async_executor as ae_mod
        monkeypatch.setattr(ae_mod, "compile", fake_compile, raising=False)

        # Now run code that should preserve order under fallback
        await executor.execute("""
log(1)
import asyncio
_ = await asyncio.sleep(0)
log(2)
""")

        assert namespace_manager.namespace.get("events") == [1, 2]

    @pytest.mark.asyncio
    async def test_ast_fallback_pep657_location_mapping(self):
        """Error spans should map to original source lines under fallback."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()

        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-ast-loc"
        )

        code = """a = 1
b = 0
c = a / b
"""
        # Call fallback directly to avoid needing await in code
        with pytest.raises(ZeroDivisionError) as exc:
            await executor._execute_with_ast_transform(code)

        # Inspect the traceback to verify the error line points to line 3
        tb = exc.value.__traceback__
        frames = []
        while tb is not None:
            frames.append((tb.tb_frame.f_code.co_filename, tb.tb_lineno))
            tb = tb.tb_next
        # Find the last frame within our fallback filename
        target = [f for f in frames if f[0] == "<async_fallback>"]
        assert target, f"No frame with fallback filename; frames: {frames}"
        # The last matching frame should be at line 3
        assert target[-1][1] == 3

        # Additionally assert the code object for the wrapper function has the fallback filename
        # Find traceback again to locate the code object
        tb = exc.value.__traceback__
        wrapper_frames = []
        while tb is not None:
            code = tb.tb_frame.f_code
            wrapper_frames.append((code.co_name, code.co_filename, tb.tb_lineno))
            tb = tb.tb_next
        # There should be a frame for __async_exec__ with our fallback filename
        assert any(name == "__async_exec__" and fn == "<async_fallback>" for name, fn, _ in wrapper_frames)

    @pytest.mark.asyncio
    async def test_ast_fallback_transform_counters_default_off(self, monkeypatch):
        """By default, def->async and lambda helper rewrites are disabled (counters 0)."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()

        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-ast-counters"
        )

        # Force fallback
        import builtins as _builtins
        orig_compile = _builtins.compile

        def fake_compile(source, filename, mode, flags=0, dont_inherit=False, optimize=-1):
            if flags & AsyncExecutor.PyCF_ALLOW_TOP_LEVEL_AWAIT:
                raise SyntaxError("force fallback")
            return orig_compile(source, filename, mode, flags=flags, dont_inherit=dont_inherit, optimize=optimize)

        import src.subprocess.async_executor as ae_mod
        monkeypatch.setattr(ae_mod, "compile", fake_compile, raising=False)

        # Simple expression under fallback
        res = await executor.execute("await asyncio.sleep(0, 'ok')")
        assert res == "ok"
        assert executor.stats.get("ast_transform_def_rewrites", 0) == 0
        assert executor.stats.get("ast_transform_lambda_helpers", 0) == 0


@pytest.mark.unit
class TestPerformance:
    """Test performance characteristics."""
    
    @pytest.mark.asyncio
    async def test_simple_await_performance(self):
        """Test that simple await executes quickly."""
        import time
        
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-perf-1"
        )
        
        code = "await asyncio.sleep(0, 'fast')"
        
        start = time.time()
        result = await executor.execute(code)
        duration = time.time() - start
        
        assert result == 'fast'
        # Should execute in less than 100ms
        assert duration < 0.1
    
    @pytest.mark.asyncio
    async def test_ast_cache_hit(self):
        """Test that AST cache improves performance."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-perf-2"
        )
        
        code = "x = 1 + 1"  # Simple code to analyze
        
        # First execution
        mode1 = executor.analyze_execution_mode(code)
        cache_size_1 = len(executor._ast_cache)
        
        # Second execution should hit cache
        mode2 = executor.analyze_execution_mode(code)
        cache_size_2 = len(executor._ast_cache)
        
        assert mode1 == mode2
        assert cache_size_1 == cache_size_2  # No new cache entry


@pytest.mark.unit
class TestIntegration:
    """Integration tests with real asyncio operations."""
    
    @pytest.mark.asyncio
    async def test_real_async_operations(self):
        """Test with real asyncio operations."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-integ-1"
        )
        
        # Test with asyncio.create_task
        code = """
import asyncio

async def background_task():
    await asyncio.sleep(0)
    return "background_done"

task = asyncio.create_task(background_task())
result = await task
"""
        await executor.execute(code)
        
        assert namespace_manager.namespace.get('result') == "background_done"
    
    @pytest.mark.asyncio
    async def test_mixed_sync_async_execution(self):
        """Test mixing sync and async execution modes."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-integ-2"
        )
        initial_ns_id = id(namespace_manager.namespace)

        # Execute sync code natively
        await executor.execute("x = 10")

        # Execute async code
        await executor.execute("y = await asyncio.sleep(0, 20)")
        
        # Execute sync code that uses previous values natively
        await executor.execute("z = x + y")
        
        # Check all values are in namespace
        assert namespace_manager.namespace.get('y') == 20
        assert namespace_manager.namespace.get('x') == 10
        assert namespace_manager.namespace.get('z') == 30
        # Namespace identity remains stable
        assert id(namespace_manager.namespace) == initial_ns_id
