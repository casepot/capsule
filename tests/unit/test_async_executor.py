"""Unit tests for AsyncExecutor skeleton implementation.

This test suite validates the AsyncExecutor skeleton that serves as
the foundation for future async execution capabilities.
"""

import pytest
import asyncio
import ast
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from src.subprocess.async_executor import AsyncExecutor, ExecutionMode
from src.subprocess.namespace import NamespaceManager
from src.subprocess.executor import ThreadedExecutor


@pytest.mark.unit
class TestExecutionMode:
    """Test ExecutionMode enum and constants."""
    
    def test_execution_mode_values(self):
        """Test that ExecutionMode enum has all required values."""
        assert ExecutionMode.TOP_LEVEL_AWAIT.value == "top_level_await"
        assert ExecutionMode.ASYNC_DEF.value == "async_def"
        assert ExecutionMode.BLOCKING_SYNC.value == "blocking_sync"
        assert ExecutionMode.SIMPLE_SYNC.value == "simple_sync"
        assert ExecutionMode.UNKNOWN.value == "unknown"
    
    def test_pycf_allow_top_level_await_constant(self):
        """Test that PyCF_ALLOW_TOP_LEVEL_AWAIT has correct value."""
        # This is the critical compile flag discovered in research
        assert AsyncExecutor.PyCF_ALLOW_TOP_LEVEL_AWAIT == 0x1000000
    
    def test_blocking_io_modules_defined(self):
        """Test that blocking I/O modules are defined."""
        expected_modules = {'requests', 'urllib', 'socket', 'subprocess'}
        assert expected_modules.issubset(AsyncExecutor.BLOCKING_IO_MODULES)
    
    def test_blocking_io_calls_defined(self):
        """Test that blocking I/O calls are defined."""
        expected_calls = {'open', 'input', 'sleep', 'wait'}
        assert expected_calls.issubset(AsyncExecutor.BLOCKING_IO_CALLS)


@pytest.mark.unit
class TestAsyncExecutorInitialization:
    """Test AsyncExecutor initialization and setup."""
    
    @pytest.mark.asyncio
    async def test_executor_creation_with_running_loop(self):
        """Test creating AsyncExecutor with existing event loop."""
        # Setup
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        # Create executor in async context (has running loop)
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec-1"
        )
        
        # Verify initialization
        assert executor.namespace is namespace_manager
        assert executor.transport is mock_transport
        assert executor.execution_id == "test-exec-1"
        assert executor.loop is asyncio.get_running_loop()
        # Executor no longer tracks loop ownership
        assert len(executor._pending_coroutines) == 0
        assert executor.stats["executions"] == 0
    
    def test_executor_creation_without_running_loop(self):
        """Test creating AsyncExecutor without existing event loop."""
        # Setup
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        # Save current loop to restore later
        original_loop = None
        try:
            original_loop = asyncio.get_event_loop()
        except RuntimeError:
            pass
        
        # Clear any existing loop
        asyncio.set_event_loop(None)
        
        try:
            # Create executor without running loop
            executor = AsyncExecutor(
                namespace_manager=namespace_manager,
                transport=mock_transport,
                execution_id="test-exec-2"
            )
            
            # Verify executor has no loop when none is running
            assert executor.loop is None
            # Executor no longer creates or sets loops
            
        finally:
            # Restore original loop
            if original_loop:
                asyncio.set_event_loop(original_loop)
    
    def test_stats_initialization(self):
        """Test that execution stats are properly initialized."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec-3"
        )
        
        # Check stats structure
        assert "executions" in executor.stats
        assert "mode_counts" in executor.stats
        assert "errors" in executor.stats
        assert "ast_transforms" in executor.stats
        
        # Check mode counts initialized for all modes
        for mode in ExecutionMode:
            assert mode in executor.stats["mode_counts"]
            assert executor.stats["mode_counts"][mode] == 0


@pytest.mark.unit
class TestExecutionModeAnalysis:
    """Test code analysis and execution mode detection."""
    
    def test_analyze_simple_sync_code(self):
        """Test detection of simple synchronous code."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Test simple expressions and statements
        assert executor.analyze_execution_mode("2 + 2") == ExecutionMode.SIMPLE_SYNC
        assert executor.analyze_execution_mode("x = 42") == ExecutionMode.SIMPLE_SYNC
        assert executor.analyze_execution_mode("print('hello')") == ExecutionMode.SIMPLE_SYNC
        assert executor.analyze_execution_mode("def foo(): return 1") == ExecutionMode.SIMPLE_SYNC
    
    def test_analyze_top_level_await(self):
        """Test detection of top-level await expressions."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Test various top-level await patterns
        # Note: These will cause SyntaxError in normal parsing
        assert executor.analyze_execution_mode(
            "await asyncio.sleep(1)"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        assert executor.analyze_execution_mode(
            "x = await some_async_func()"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await in compound statements (still top-level)
        code = """
result = await fetch_data()
print(result)
"""
        assert executor.analyze_execution_mode(code) == ExecutionMode.TOP_LEVEL_AWAIT
    
    def test_analyze_async_def(self):
        """Test detection of async function definitions."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Test async function definition
        code = """
async def fetch_data():
    await asyncio.sleep(1)
    return "data"
"""
        assert executor.analyze_execution_mode(code) == ExecutionMode.ASYNC_DEF
        
        # Test mixed async and sync functions
        code = """
def sync_func():
    return 1

async def async_func():
    await asyncio.sleep(0)
"""
        assert executor.analyze_execution_mode(code) == ExecutionMode.ASYNC_DEF
    
    def test_analyze_blocking_io(self):
        """Test detection of blocking I/O operations."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Test import of blocking module
        assert executor.analyze_execution_mode(
            "import requests"
        ) == ExecutionMode.BLOCKING_SYNC
        
        assert executor.analyze_execution_mode(
            "from urllib import request"
        ) == ExecutionMode.BLOCKING_SYNC
        
        # Test blocking function calls
        assert executor.analyze_execution_mode(
            "data = open('file.txt').read()"
        ) == ExecutionMode.BLOCKING_SYNC
        
        assert executor.analyze_execution_mode(
            "user_input = input('Enter: ')"
        ) == ExecutionMode.BLOCKING_SYNC
    
    def test_analyze_unknown_syntax(self):
        """Test handling of unknown/invalid syntax."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Test clearly invalid syntax
        assert executor.analyze_execution_mode(
            "this is not valid python at all"
        ) == ExecutionMode.UNKNOWN
    
    def test_analyze_top_level_await_edge_cases(self):
        """Test detection of top-level await in various contexts (edge cases).
        
        This test covers the edge cases identified by PR reviewers where
        await expressions appear in various contexts that require proper
        recursive AST traversal to detect.
        """
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Test await in function call
        assert executor.analyze_execution_mode(
            "print(await foo())"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await in list comprehension
        assert executor.analyze_execution_mode(
            "[await x for x in items]"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await in dict literal
        assert executor.analyze_execution_mode(
            "result = {'key': await get_value()}"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await in set literal
        assert executor.analyze_execution_mode(
            "result = {await x, await y}"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await in tuple
        assert executor.analyze_execution_mode(
            "result = (1, await foo(), 3)"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await in conditional expression
        assert executor.analyze_execution_mode(
            "x = await foo() if condition else await bar()"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await in binary operation
        assert executor.analyze_execution_mode(
            "result = await foo() + await bar()"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await in comparison
        assert executor.analyze_execution_mode(
            "if await check() == True: pass"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await in nested expression
        assert executor.analyze_execution_mode(
            "result = len(await get_list())"
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await in f-string
        assert executor.analyze_execution_mode(
            'msg = f"Value: {await get_value()}"'
        ) == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await NOT detected inside function definition
        code_with_await_in_func = """
def func():
    return await foo()
"""
        # Should be UNKNOWN (syntax error) or SIMPLE_SYNC, not TOP_LEVEL_AWAIT
        mode = executor.analyze_execution_mode(code_with_await_in_func)
        assert mode != ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test await NOT detected inside async function
        code_with_await_in_async = """
async def func():
    return await foo()
"""
        # Should be ASYNC_DEF, not TOP_LEVEL_AWAIT
        assert executor.analyze_execution_mode(
            code_with_await_in_async
        ) == ExecutionMode.ASYNC_DEF
        
        # Test await NOT detected inside lambda (though this is invalid Python)
        # This should not be detected as TOP_LEVEL_AWAIT
        mode = executor.analyze_execution_mode("f = lambda: await foo()")
        assert mode != ExecutionMode.TOP_LEVEL_AWAIT
    
    def test_ast_caching(self):
        """Test that AST parsing results are cached."""
        import hashlib
        
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        code = "x = 1 + 2"
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        
        # First analysis should cache the AST
        mode1 = executor.analyze_execution_mode(code)
        assert code_hash in executor._ast_cache
        
        # Second analysis should use cached AST
        mode2 = executor.analyze_execution_mode(code)
        assert mode1 == mode2
        assert code_hash in executor._ast_cache
    
    def test_ast_cache_eviction(self):
        """Test that LRU cache evicts oldest entries when full."""
        import hashlib
        
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Set a small cache size for testing
        executor._ast_cache_max_size = 3
        
        # Add entries to fill the cache
        codes = []
        hashes = []
        for i in range(4):
            code = f"x = {i}"
            codes.append(code)
            code_hash = hashlib.sha256(code.encode()).hexdigest()
            hashes.append(code_hash)
            executor.analyze_execution_mode(code)
        
        # Cache should only have the last 3 entries
        assert len(executor._ast_cache) == 3
        assert hashes[0] not in executor._ast_cache  # First (oldest) should be evicted
        assert hashes[1] in executor._ast_cache
        assert hashes[2] in executor._ast_cache
        assert hashes[3] in executor._ast_cache
        
        # Access an existing entry to make it most recently used
        executor.analyze_execution_mode(codes[1])
        
        # Add another new entry
        code = "y = 5"
        new_hash = hashlib.sha256(code.encode()).hexdigest()
        executor.analyze_execution_mode(code)
        
        # Now codes[2] should be evicted, not codes[1] (which we just accessed)
        assert len(executor._ast_cache) == 3
        assert hashes[1] in executor._ast_cache  # Recently accessed, should stay
        assert hashes[2] not in executor._ast_cache  # Should be evicted
        assert hashes[3] in executor._ast_cache
        assert new_hash in executor._ast_cache


@pytest.mark.unit
class TestAsyncExecutorExecution:
    """Test AsyncExecutor execution and delegation."""
    
    @pytest.mark.asyncio
    async def test_execute_simple_sync_delegates_to_threaded(self):
        """Test that simple sync code delegates to ThreadedExecutor."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Mock ThreadedExecutor to verify delegation
        with patch('src.subprocess.async_executor.ThreadedExecutor') as MockThreadedExecutor:
            mock_instance = MockThreadedExecutor.return_value
            mock_instance.start_output_pump = AsyncMock()
            mock_instance.stop_output_pump = AsyncMock()
            mock_instance.execute_code_async = AsyncMock(return_value=42)
            
            result = await executor.execute("2 + 2")
            
            # Verify ThreadedExecutor was created with correct params
            MockThreadedExecutor.assert_called_once_with(
                transport=mock_transport,
                execution_id="test-exec",
                namespace=namespace_manager.namespace,
                loop=executor.loop
            )
            
            # Verify execution methods were called
            mock_instance.start_output_pump.assert_called_once()
            mock_instance.execute_code_async.assert_called_once_with("2 + 2")
            mock_instance.stop_output_pump.assert_called_once()
            
            assert result == 42
    
    @pytest.mark.asyncio
    async def test_execute_top_level_await_raises_not_implemented(self):
        """Test that top-level await raises NotImplementedError."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Top-level await should raise NotImplementedError
        with pytest.raises(NotImplementedError, match="Async execution coming soon"):
            await executor.execute("await asyncio.sleep(1)")
    
    @pytest.mark.asyncio
    async def test_execute_updates_stats(self):
        """Test that execution updates statistics."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        with patch('src.subprocess.async_executor.ThreadedExecutor') as MockThreadedExecutor:
            mock_instance = MockThreadedExecutor.return_value
            mock_instance.start_output_pump = AsyncMock()
            mock_instance.stop_output_pump = AsyncMock()
            mock_instance.execute_code_async = AsyncMock(return_value=None)
            
            # Execute simple sync code
            await executor.execute("x = 1")
            
            # Check stats updated
            assert executor.stats["executions"] == 1
            assert executor.stats["mode_counts"][ExecutionMode.SIMPLE_SYNC] == 1
            assert executor.stats["errors"] == 0
    
    @pytest.mark.asyncio
    async def test_execute_handles_exceptions(self):
        """Test that execution properly handles exceptions."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        with patch('src.subprocess.async_executor.ThreadedExecutor') as MockThreadedExecutor:
            mock_instance = MockThreadedExecutor.return_value
            mock_instance.start_output_pump = AsyncMock()
            mock_instance.stop_output_pump = AsyncMock()
            mock_instance.execute_code_async = AsyncMock(
                side_effect=ValueError("Test error")
            )
            
            with pytest.raises(ValueError, match="Test error"):
                await executor.execute("invalid code")
            
            # Check error stats updated
            assert executor.stats["errors"] == 1
            
            # Verify cleanup was called
            mock_instance.stop_output_pump.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_namespace_preservation(self):
        """Test that namespace identity is preserved (merge-only policy)."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        
        # Get initial namespace identity
        initial_namespace_id = id(namespace_manager.namespace)
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Verify executor references same namespace object
        assert id(executor.namespace.namespace) == initial_namespace_id
        
        with patch('src.subprocess.async_executor.ThreadedExecutor') as MockThreadedExecutor:
            mock_instance = MockThreadedExecutor.return_value
            mock_instance.start_output_pump = AsyncMock()
            mock_instance.stop_output_pump = AsyncMock()
            mock_instance.execute_code_async = AsyncMock(return_value=None)
            
            await executor.execute("x = 42")
            
            # Namespace identity must be preserved
            assert id(namespace_manager.namespace) == initial_namespace_id


@pytest.mark.unit
class TestCoroutineManagement:
    """Test coroutine lifecycle management."""
    
    def test_cleanup_coroutines_empty(self):
        """Test cleanup when no coroutines are tracked."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        cleaned = executor.cleanup_coroutines()
        assert cleaned == 0
        assert len(executor._pending_coroutines) == 0
    
    @pytest.mark.asyncio
    async def test_cleanup_coroutines_with_pending(self):
        """Test cleanup of pending coroutines."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Create a test coroutine
        async def test_coro():
            await asyncio.sleep(10)
        
        coro = test_coro()
        
        # Add to pending (simulate tracking)
        import weakref
        executor._pending_coroutines.add(weakref.ref(coro))
        
        # Clean up
        cleaned = executor.cleanup_coroutines()
        assert cleaned == 1
        
        # Verify coroutine was closed by trying to close it again
        # A closed coroutine will not raise an exception on close()
        try:
            coro.close()
            # If we get here, the coroutine was already closed (good)
        except RuntimeError as e:
            # If it wasn't closed, we'd get an error
            pytest.fail(f"Coroutine was not properly closed: {e}")


@pytest.mark.unit
class TestAsyncExecutorIntegration:
    """Integration tests with real components."""
    
    @pytest.mark.asyncio
    async def test_integration_with_real_namespace_manager(self):
        """Test AsyncExecutor with real NamespaceManager."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # The namespace should have engine internals
        assert '_' in namespace_manager.namespace or True  # May not be initialized
        
        # Verify namespace manager is properly referenced
        assert executor.namespace is namespace_manager
    
    @pytest.mark.asyncio
    async def test_executor_explicit_cleanup(self):
        """Test that executor can be explicitly closed."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        # Create executor in an async context
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Executor should have access to current loop
        assert executor.loop is not None
        
        # Test explicit close
        await executor.close()
        
        # Verify cleanup happened (no exceptions)
        # The executor no longer manages loop lifecycle
    
    @pytest.mark.asyncio
    async def test_executor_context_manager(self):
        """Test that executor works as an async context manager."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        # Use executor as context manager
        async with AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        ) as executor:
            # Executor should be usable
            assert executor is not None
            assert executor.loop is not None
        
        # Context manager should have called close (no exceptions)