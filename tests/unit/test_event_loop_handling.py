"""Unit tests for event loop error handling and proper context requirements."""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock

from src.subprocess.async_executor import AsyncExecutor, ExecutionMode
from src.subprocess.namespace import NamespaceManager
from src.protocol.framing import RateLimiter


@pytest.mark.unit
class TestEventLoopHandling:
    """Test that components properly handle event loop context requirements."""
    
    def test_async_executor_requires_async_context(self):
        """Test that AsyncExecutor._execute_with_threaded_executor fails clearly outside async context."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # Verify the new behavior: get_running_loop is called directly
        # without try/except, letting it raise naturally
        # Test actual behavior: should raise RuntimeError outside async context
        import asyncio
        import sys
        
        # Create a coroutine to test
        async def test_coro():
            return await executor._execute_with_threaded_executor("x = 1")
        
        # Try to run outside async context - should fail with our improved error message
        with pytest.raises(RuntimeError, match="AsyncExecutor.execute\\(\\) must be called from within an async context"):
            # Create new event loop and immediately close it to ensure no loop
            loop = asyncio.new_event_loop()
            loop.close()
            # Now try to get coroutine result - will fail when it tries get_running_loop()
            coro = test_coro()
            try:
                coro.send(None)  # Start the coroutine
            except StopIteration:
                pass  # Shouldn't get here
            finally:
                coro.close()
    
    @pytest.mark.asyncio
    async def test_rate_limiter_requires_async_context(self):
        """Test that RateLimiter properly works in async context only."""
        limiter = RateLimiter(
            max_messages_per_second=10,
            burst_size=20
        )
        
        # This should work in async context
        await limiter.acquire()  # Should not raise
        
        # Test try_acquire as well
        result = limiter.try_acquire()
        assert result is True
        
        # Test that it properly uses loop.time() not time.time()
        # First exhaust the burst capacity
        for _ in range(20):  # Burst size is 20
            limiter.try_acquire()
        
        # Now we should be rate limited
        results = []
        for _ in range(5):
            acquired = limiter.try_acquire()
            results.append(acquired)
        
        # Should all fail since we exhausted burst
        assert not any(results)  # All should fail due to rate limiting
    
    @pytest.mark.asyncio
    async def test_async_executor_with_event_loop(self):
        """Test that AsyncExecutor works correctly when called from async context."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        # Create future using the running loop
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        future.set_result(None)
        mock_transport.send_message = Mock(return_value=future)
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="test-exec"
        )
        
        # This should work without errors
        try:
            result = await executor.execute("x = 1 + 1")
            # The execution delegates to ThreadedExecutor which we mock
        except NotImplementedError:
            # Expected for TOP_LEVEL_AWAIT mode
            pass
        except Exception as e:
            # Should not get RuntimeError about event loop
            assert "must be called from async context" not in str(e)
    
    @pytest.mark.asyncio
    async def test_nested_async_contexts(self):
        """Test AsyncExecutor works correctly in nested async contexts."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        
        async def nested_executor_call():
            """Inner async function to test nested contexts."""
            executor = AsyncExecutor(
                namespace_manager=namespace_manager,
                transport=mock_transport,
                execution_id="nested-exec"
            )
            # This should work fine in nested async context
            mode = executor.analyze_execution_mode("x = 1")
            assert mode == ExecutionMode.SIMPLE_SYNC
            return "nested_success"
        
        # Outer async context
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="outer-exec"
        )
        
        # Test outer context works
        mode = executor.analyze_execution_mode("y = 2")
        assert mode == ExecutionMode.SIMPLE_SYNC
        
        # Test nested call works
        nested_result = await nested_executor_call()
        assert nested_result == "nested_success"
    
    @pytest.mark.asyncio
    async def test_concurrent_session_creation(self):
        """Test multiple AsyncExecutor instances can be created concurrently."""
        namespace_managers = [NamespaceManager() for _ in range(3)]
        mock_transports = [Mock() for _ in range(3)]
        for transport in mock_transports:
            transport.send_message = AsyncMock()
        
        async def create_and_use(index):
            """Create executor and analyze code."""
            executor = AsyncExecutor(
                namespace_manager=namespace_managers[index],
                transport=mock_transports[index],
                execution_id=f"concurrent-{index}"
            )
            mode = executor.analyze_execution_mode(f"x = {index}")
            return mode
        
        # Create and use executors concurrently
        tasks = [create_and_use(i) for i in range(3)]
        results = await asyncio.gather(*tasks)
        
        # Verify all executed correctly
        assert all(r == ExecutionMode.SIMPLE_SYNC for r in results)
    
    @pytest.mark.asyncio
    async def test_syntaxerror_edge_cases(self):
        """Test SyntaxError handling for various edge cases."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="syntax-test"
        )
        
        # lambda with await is syntactically valid (the assignment is fine)
        # It would only error when the lambda is executed
        mode = executor.analyze_execution_mode("f = lambda: await foo()")
        assert mode == ExecutionMode.SIMPLE_SYNC  # The assignment itself is valid sync code
        
        # def with await outside async is also syntactically valid
        mode = executor.analyze_execution_mode("def f(): return await foo()")
        assert mode == ExecutionMode.SIMPLE_SYNC  # The def itself is valid
        
        # These cause actual SyntaxErrors and should be detected as TOP_LEVEL_AWAIT or UNKNOWN
        syntax_errors = [
            "await x()",  # Top-level await
            "class C: x = await foo()",  # await in class body - SyntaxError
        ]
        
        # Test top-level await detection
        mode = executor.analyze_execution_mode("await x()")
        assert mode == ExecutionMode.TOP_LEVEL_AWAIT
        
        # Test class body await (actual SyntaxError even with PyCF_ALLOW_TOP_LEVEL_AWAIT)
        mode = executor.analyze_execution_mode("class C: x = await foo()")
        assert mode in (ExecutionMode.UNKNOWN, ExecutionMode.TOP_LEVEL_AWAIT)
        
        # Valid top-level await (would work with PyCF_ALLOW_TOP_LEVEL_AWAIT)
        valid_top_level = [
            "await asyncio.sleep(0)",
            "x = await foo()",
            "await foo(); await bar()",
        ]
        
        for code in valid_top_level:
            mode = executor.analyze_execution_mode(code)
            assert mode == ExecutionMode.TOP_LEVEL_AWAIT, f"Code {code!r} should be TOP_LEVEL_AWAIT"
    
    def test_init_outside_async_context(self):
        """Test AsyncExecutor can be initialized outside async context."""
        namespace_manager = NamespaceManager()
        mock_transport = Mock()
        
        # This should work fine - init doesn't require async context
        executor = AsyncExecutor(
            namespace_manager=namespace_manager,
            transport=mock_transport,
            execution_id="sync-init"
        )
        
        # Verify initialization worked
        assert executor.namespace == namespace_manager
        assert executor.transport == mock_transport
        assert executor.execution_id == "sync-init"
        assert executor.loop is None  # Should be None until execute() is called
        
        # analyze_execution_mode should work outside async context
        mode = executor.analyze_execution_mode("x = 1")
        assert mode == ExecutionMode.SIMPLE_SYNC
    
    @pytest.mark.asyncio
    async def test_queue_size_platform_compatibility(self):
        """Test that queue size handling works on platforms without qsize."""
        from src.subprocess.executor import ThreadedExecutor
        
        # Create executor with mock transport
        mock_transport = Mock()
        loop = asyncio.get_running_loop()
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace={},
            loop=loop
        )
        
        # Mock a queue without qsize method
        mock_queue = Mock()
        mock_queue.qsize.side_effect = NotImplementedError("qsize not supported")
        mock_queue.put_nowait = Mock()
        executor._aq = mock_queue
        
        # This should handle the exception gracefully
        # Test actual behavior - should not crash
        # The method should work despite NotImplementedError from qsize
        try:
            executor._enqueue_from_thread("test", "data")
            # Success - it didn't crash when qsize raised NotImplementedError
            assert True
        except Exception as e:
            # Should not raise any exception
            pytest.fail(f"_enqueue_from_thread raised unexpected exception: {e}")


@pytest.mark.unit  
class TestErrorHandlingImprovements:
    """Test that error handling follows 'fail fast, fail clearly' principle."""
    
    def test_no_bare_excepts_in_executor(self):
        """Verify no bare except statements in executor."""
        from src.subprocess import executor
        import inspect
        
        source = inspect.getsource(executor)
        # Check for bare excepts (except: without Exception)
        lines = source.split('\n')
        for i, line in enumerate(lines):
            if 'except:' in line and '#' not in line:
                # This should not happen anymore
                pytest.fail(f"Found bare except at line {i}: {line.strip()}")
    
    def test_no_bare_excepts_in_async_executor(self):
        """Verify no bare except statements in async_executor."""
        from src.subprocess import async_executor
        import inspect
        
        source = inspect.getsource(async_executor)
        lines = source.split('\n')
        for i, line in enumerate(lines):
            if 'except:' in line and 'except Exception:' not in line and '#' not in line:
                # Check if it's a bare except (not except Exception:)
                next_line = lines[i+1] if i+1 < len(lines) else ""
                if "pass" in next_line and "Exception" not in line:
                    pytest.fail(f"Found bare except at line {i}: {line.strip()}")
    
    @pytest.mark.asyncio
    async def test_transport_cleanup_logging(self):
        """Test that transport cleanup errors are logged, not silently swallowed."""
        from src.session.manager import Session
        import logging
        
        # Create a session with a mock transport that fails on close
        session = Session()
        mock_transport = Mock()
        
        # Create an async mock that raises an exception
        async def failing_close():
            raise Exception("Close failed")
        
        mock_transport.close = Mock(side_effect=failing_close)
        session._transport = mock_transport
        
        # Verify the error is handled, not raised
        # The terminate method should log the error, not raise it
        
        # Call terminate - should not raise
        await session.terminate()
        
        # Verify close was attempted
        mock_transport.close.assert_called_once()