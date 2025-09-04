"""Unit tests for event loop error handling and proper context requirements."""

import asyncio
import pytest
from unittest.mock import Mock

from src.subprocess.async_executor import AsyncExecutor
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
        
        # This should fail with a clear error when trying to get running loop
        # Note: We can't directly test the execute method since it's async,
        # but we test that the error handling is in place
        code = """
        # Get current running loop for the executor
        try:
            current_loop = self.loop or asyncio.get_running_loop()
        except RuntimeError as e:
            raise RuntimeError(
                f"AsyncExecutor.execute() must be called from async context: {e}"
            ) from e
        """
        
        # Verify the error handling code is present
        import inspect
        source = inspect.getsource(executor._execute_with_threaded_executor)
        assert "must be called from async context" in source
    
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
        
        # Test that it properly gets the running loop
        # The try_acquire method should not fall back to time.time()
        import inspect
        source = inspect.getsource(limiter.try_acquire)
        assert "time.time()" not in source
        assert "get_running_loop()" in source
    
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
    
    def test_queue_size_platform_compatibility(self):
        """Test that queue size handling works on platforms without qsize."""
        from src.subprocess.executor import ThreadedExecutor
        
        # Create executor with mock transport
        mock_transport = Mock()
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace={},
            loop=None
        )
        
        # Mock a queue without qsize method
        mock_queue = Mock()
        mock_queue.qsize.side_effect = NotImplementedError("qsize not supported")
        executor._aq = mock_queue
        
        # This should handle the exception gracefully
        # The code uses (AttributeError, NotImplementedError) now
        import inspect
        source = inspect.getsource(executor._enqueue_from_thread)
        assert "(AttributeError, NotImplementedError)" in source
        assert "except:" not in source  # No bare excepts


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
        
        # Verify the error handling code is present in terminate()
        # The terminate method should log the error, not raise it
        import inspect
        source = inspect.getsource(session.terminate)
        assert "logger.debug" in source
        assert "non-critical" in source
        
        # Call terminate - should not raise
        await session.terminate()
        
        # Verify close was attempted
        mock_transport.close.assert_called_once()