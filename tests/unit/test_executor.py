"""Unit tests for ThreadedExecutor."""

import pytest
import asyncio
import sys
import threading
from unittest.mock import Mock, AsyncMock, MagicMock
from src.subprocess.executor import ThreadedExecutor, CancelToken


@pytest.mark.unit
class TestThreadedExecutor:
    """Test ThreadedExecutor functionality."""
    
    @pytest.mark.asyncio
    async def test_executor_creation(self):
        """Test creating a threaded executor."""
        mock_transport = Mock()
        loop = asyncio.get_event_loop()
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace={},
            loop=loop
        )
        
        assert executor._execution_id == "test-exec"
        assert executor._namespace == {}
        assert executor._cancel_token is not None
        assert executor._loop is loop
    
    @pytest.mark.asyncio
    async def test_simple_code_execution(self):
        """Test executing simple Python code."""
        mock_transport = Mock()
        # Make send_message an async mock so it can be awaited
        mock_transport.send_message = AsyncMock()
        loop = asyncio.get_event_loop()
        namespace = {}
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace=namespace,
            loop=loop
        )
        
        # Start output pump
        await executor.start_output_pump()
        
        try:
            result = await executor.execute_code_async("2 + 2")
            assert result == 4
            
            # Check namespace wasn't polluted
            assert "_" not in namespace or namespace["_"] == 4
        finally:
            await executor.stop_output_pump()
    
    @pytest.mark.asyncio
    async def test_namespace_modification(self):
        """Test that executor modifies namespace."""
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        loop = asyncio.get_event_loop()
        namespace = {}
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace=namespace,
            loop=loop
        )
        
        await executor.start_output_pump()
        
        try:
            await executor.execute_code_async("x = 42")
            assert namespace["x"] == 42
            
            result = await executor.execute_code_async("x * 2")
            assert result == 84
        finally:
            await executor.stop_output_pump()
    
    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Test exception handling during execution."""
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        loop = asyncio.get_event_loop()
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace={},
            loop=loop
        )
        
        await executor.start_output_pump()
        
        try:
            with pytest.raises(ZeroDivisionError):
                await executor.execute_code_async("1/0")
        finally:
            await executor.stop_output_pump()
    
    @pytest.mark.asyncio
    async def test_output_capture(self):
        """Test stdout/stderr capture during execution."""
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        loop = asyncio.get_event_loop()
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace={},
            loop=loop
        )
        
        # Start output pump
        await executor.start_output_pump()
        
        try:
            # Execute code with print
            await executor.execute_code_async("print('hello world')")
            
            # Allow pump to process
            await asyncio.sleep(0.1)
            
            # Check transport received output message
            # With AsyncMock, we can verify send_message was called
            assert mock_transport.send_message.called  # Output was sent
        finally:
            await executor.stop_output_pump()
    
    @pytest.mark.asyncio
    async def test_cancellation(self):
        """Test code execution cancellation."""
        mock_transport = Mock()
        mock_transport.send_message = AsyncMock()
        loop = asyncio.get_event_loop()
        
        executor = ThreadedExecutor(
            transport=mock_transport,
            execution_id="test-exec",
            namespace={},
            loop=loop,
            enable_cooperative_cancel=True,
            cancel_check_interval=10  # Check frequently for test
        )
        
        await executor.start_output_pump()
        
        try:
            # Start long-running execution
            exec_task = asyncio.create_task(
                executor.execute_code_async("""
count = 0
while count < 1000000:
    count += 1
""")
            )
            
            # Cancel after short delay
            await asyncio.sleep(0.05)
            executor.cancel()
            
            # Should raise KeyboardInterrupt
            with pytest.raises(KeyboardInterrupt):
                await exec_task
        finally:
            await executor.stop_output_pump()


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
    
    def test_cancel_token_reset(self):
        """Test resetting cancel token."""
        token = CancelToken()
        token.cancel()
        assert token.is_cancelled()
        token.reset()
        assert not token.is_cancelled()
    
    def test_cancel_token_thread_safe(self):
        """Test cancel token is thread-safe."""
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