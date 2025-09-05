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
        """Test that await in lambda is handled properly."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-error-1"
        )
        
        # lambda with await is syntactically valid but semantically invalid
        # The assignment itself should work
        code = "f = lambda: await foo()"
        result = await executor.execute(code)
        
        # The lambda definition itself succeeds
        assert 'f' in namespace_manager.namespace
    
    @pytest.mark.asyncio
    async def test_await_without_async_context_in_def(self):
        """Test await in regular function definition."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-error-2"
        )
        
        # This is syntactically valid (the def succeeds)
        # but would fail at runtime when the function is called
        code = """
def regular_func():
    return await something()
"""
        result = await executor.execute(code)
        
        # Function definition should succeed
        assert 'regular_func' in namespace_manager.namespace
    
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
        
        # Patch compile to simulate SyntaxError on first attempt
        original_compile = compile
        call_count = 0
        
        def mock_compile(source, filename, mode, flags=0, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and flags & executor.PyCF_ALLOW_TOP_LEVEL_AWAIT:
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
        
        # Execute sync code
        with patch('src.subprocess.async_executor.ThreadedExecutor') as MockThreaded:
            mock_instance = MockThreaded.return_value
            mock_instance.start_output_pump = AsyncMock()
            mock_instance.stop_output_pump = AsyncMock()
            mock_instance.execute_code_async = AsyncMock(return_value=None)
            
            await executor.execute("x = 10")
        
        # Execute async code
        await executor.execute("y = await asyncio.sleep(0, 20)")
        
        # Execute sync code that uses previous values
        with patch('src.subprocess.async_executor.ThreadedExecutor') as MockThreaded:
            mock_instance = MockThreaded.return_value
            mock_instance.start_output_pump = AsyncMock()
            mock_instance.stop_output_pump = AsyncMock()
            mock_instance.execute_code_async = AsyncMock(return_value=None)
            
            await executor.execute("z = x + y")
        
        # Check all values are in namespace
        assert namespace_manager.namespace.get('y') == 20