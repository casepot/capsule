"""Unit tests for ThreadedExecutor."""

import pytest
import asyncio
import sys
from unittest.mock import Mock, AsyncMock, patch
from src.subprocess.executor import ThreadedExecutor, ThreadSafeOutput, CancelToken


@pytest.mark.unit
class TestThreadedExecutor:
    """Test ThreadedExecutor functionality."""
    
    @pytest.mark.asyncio
    async def test_executor_creation(self):
        """Test creating a threaded executor."""
        mock_transport = AsyncMock()
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace={}
        )
        
        assert executor.execution_id == "test-exec"
        assert executor._namespace == {}
        assert executor._cancel_token is not None
    
    @pytest.mark.asyncio
    async def test_simple_code_execution(self):
        """Test executing simple Python code."""
        mock_transport = AsyncMock()
        namespace = {}
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace=namespace
        )
        
        result = await executor.execute_code("2 + 2")
        assert result == 4
        
        # Check namespace wasn't polluted
        assert "2" not in namespace
    
    @pytest.mark.asyncio
    async def test_namespace_modification(self):
        """Test that executor modifies namespace."""
        mock_transport = AsyncMock()
        namespace = {}
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace=namespace
        )
        
        await executor.execute_code("x = 42")
        assert namespace["x"] == 42
        
        result = await executor.execute_code("x * 2")
        assert result == 84
    
    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Test exception handling during execution."""
        mock_transport = AsyncMock()
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace={}
        )
        
        with pytest.raises(ZeroDivisionError):
            await executor.execute_code("1/0")
    
    @pytest.mark.asyncio
    async def test_output_capture(self):
        """Test stdout/stderr capture during execution."""
        mock_transport = AsyncMock()
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace={}
        )
        
        # Start output pump
        executor.start_output_pump()
        
        # Execute code with print
        await executor.execute_code("print('hello world')")
        
        # Drain outputs
        await executor.drain_outputs()
        
        # Check transport received output message
        mock_transport.send.assert_called()
        
        # Stop pump
        executor.stop_output_pump()
    
    @pytest.mark.asyncio
    async def test_cancellation(self):
        """Test code execution cancellation."""
        mock_transport = AsyncMock()
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace={},
            enable_cooperative_cancel=True
        )
        
        # Start long-running execution
        exec_task = asyncio.create_task(
            executor.execute_code("while True: pass")
        )
        
        # Cancel after short delay
        await asyncio.sleep(0.1)
        executor.cancel()
        
        # Should raise KeyboardInterrupt
        with pytest.raises(KeyboardInterrupt):
            await exec_task


@pytest.mark.unit
class TestCancelToken:
    """Test CancelToken functionality."""
    
    def test_cancel_token_creation(self):
        """Test creating a cancel token."""
        token = CancelToken()
        assert not token.is_cancelled()
    
    def test_cancel_token_set(self):
        """Test setting cancel token."""
        token = CancelToken()
        token.cancel()
        assert token.is_cancelled()
    
    def test_cancel_token_clear(self):
        """Test clearing cancel token."""
        token = CancelToken()
        token.cancel()
        assert token.is_cancelled()
        token.clear()
        assert not token.is_cancelled()
    
    def test_cancel_token_thread_safe(self):
        """Test cancel token is thread-safe."""
        import threading
        
        token = CancelToken()
        results = []
        
        def check_and_set():
            results.append(token.is_cancelled())
            token.cancel()
            results.append(token.is_cancelled())
        
        threads = [threading.Thread(target=check_and_set) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All threads should see consistent state after cancellation
        assert all(results[i] for i in range(1, len(results), 2))