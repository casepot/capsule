"""Tests for unified output handling with ThreadSafeOutput."""

import asyncio
import pytest
import sys
import time
import uuid
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from io import StringIO
from typing import Any, Dict

from src.protocol.messages import OutputMessage, StreamType
from src.protocol.transport import MessageTransport
from src.subprocess.executor import ThreadedExecutor, ThreadSafeOutput
from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, ResultMessage, ErrorMessage


class TestThreadSafeOutputAttributes:
    """Test TextIOBase-compatible attributes."""
    
    def test_encoding_attribute(self):
        """Test that ThreadSafeOutput has encoding attribute."""
        executor = Mock()
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        assert hasattr(output, 'encoding')
        assert output.encoding == "utf-8"
    
    def test_errors_attribute(self):
        """Test that ThreadSafeOutput has errors attribute."""
        executor = Mock()
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        assert hasattr(output, 'errors')
        assert output.errors == "replace"
    
    def test_writable_method(self):
        """Test that ThreadSafeOutput has writable() method."""
        executor = Mock()
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        assert hasattr(output, 'writable')
        assert callable(output.writable)
        assert output.writable() is True
    
    def test_library_compatibility(self):
        """Test that libraries expecting TextIOBase attributes work."""
        executor = Mock()
        executor._enqueue_from_thread = Mock()
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        # Simulate library checking stdout attributes
        encoding = getattr(output, 'encoding', None)
        errors = getattr(output, 'errors', None)
        is_writable = output.writable() if hasattr(output, 'writable') else False
        
        assert encoding == "utf-8"
        assert errors == "replace"
        assert is_writable is True


class TestProgressBarHandling:
    """Test carriage return handling for progress bars."""
    
    def test_carriage_return_handling(self):
        """Test that carriage returns are handled correctly for progress bars."""
        executor = Mock()
        executor._line_chunk_size = 64 * 1024  # Set chunk size
        enqueued = []
        executor._enqueue_from_thread = lambda data, stream: enqueued.append((data, stream))
        
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        # Simulate tqdm-like progress output
        output.write("Progress: 0%\r")
        output.write("Progress: 25%\r")
        output.write("Progress: 50%\r")
        output.write("Progress: 75%\r")
        output.write("Progress: 100%\n")
        
        # Should have sent 4 CR updates and 1 final line with newline
        assert len(enqueued) == 5
        assert enqueued[0] == ("Progress: 0%\r", StreamType.STDOUT)
        assert enqueued[1] == ("Progress: 25%\r", StreamType.STDOUT)
        assert enqueued[2] == ("Progress: 50%\r", StreamType.STDOUT) 
        assert enqueued[3] == ("Progress: 75%\r", StreamType.STDOUT)
        assert enqueued[4] == ("Progress: 100%\n", StreamType.STDOUT)
    
    def test_mixed_cr_and_newline(self):
        """Test handling of mixed carriage returns and newlines."""
        executor = Mock()
        executor._line_chunk_size = 64 * 1024  # Set chunk size
        enqueued = []
        executor._enqueue_from_thread = lambda data, stream: enqueued.append((data, stream))
        
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        # Mix of CR and newline
        output.write("Step 1\n")
        output.write("Progress: 0%\r")
        output.write("Progress: 50%\r")
        output.write("Progress: 100%\n")
        output.write("Step 2\n")
        
        assert len(enqueued) == 5
        assert enqueued[0] == ("Step 1\n", StreamType.STDOUT)
        assert enqueued[1] == ("Progress: 0%\r", StreamType.STDOUT)
        assert enqueued[2] == ("Progress: 50%\r", StreamType.STDOUT)
        assert enqueued[3] == ("Progress: 100%\n", StreamType.STDOUT)
        assert enqueued[4] == ("Step 2\n", StreamType.STDOUT)
    
    def test_cr_overwrites_buffer(self):
        """Test that CR properly overwrites buffered content."""
        executor = Mock()
        executor._line_chunk_size = 64 * 1024  # Set chunk size
        enqueued = []
        executor._enqueue_from_thread = lambda data, stream: enqueued.append((data, stream))
        
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        # Write partial line, then CR to overwrite
        output.write("Old content")
        output.write("\r")
        output.write("New content\n")
        
        # Should send "Old content\r" then "New content\n"
        assert len(enqueued) == 2
        assert enqueued[0] == ("Old content\r", StreamType.STDOUT)
        assert enqueued[1] == ("New content\n", StreamType.STDOUT)


class TestLongLineChunking:
    """Test chunking of very long lines."""
    
    def test_long_line_chunking(self):
        """Test that lines over 64KB are chunked properly."""
        executor = Mock()
        executor._line_chunk_size = 100  # Small chunk size for testing
        enqueued = []
        executor._enqueue_from_thread = lambda data, stream: enqueued.append((data, stream))
        
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        # Create a line longer than chunk size
        long_line = "x" * 250
        output.write(long_line + "\n")
        
        # Should be chunked into 3 pieces (100, 100, 50+newline)
        assert len(enqueued) == 3
        assert enqueued[0] == ("x" * 100, StreamType.STDOUT)
        assert enqueued[1] == ("x" * 100, StreamType.STDOUT)
        assert enqueued[2] == ("x" * 50 + "\n", StreamType.STDOUT)
    
    def test_exact_chunk_boundary(self):
        """Test line that exactly matches chunk size."""
        executor = Mock()
        executor._line_chunk_size = 100
        enqueued = []
        executor._enqueue_from_thread = lambda data, stream: enqueued.append((data, stream))
        
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        # Exactly 100 chars
        line = "x" * 100
        output.write(line + "\n")
        
        # Should send as single chunk with newline
        assert len(enqueued) == 1
        assert enqueued[0] == (line + "\n", StreamType.STDOUT)
    
    def test_multi_mb_output(self):
        """Test handling of multi-megabyte output."""
        executor = Mock()
        executor._line_chunk_size = 64 * 1024  # 64KB chunks
        enqueued = []
        executor._enqueue_from_thread = lambda data, stream: enqueued.append((data, stream))
        
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        # Create 2MB line
        mb_line = "x" * (2 * 1024 * 1024)
        output.write(mb_line + "\n")
        
        # Calculate expected chunks
        chunk_size = 64 * 1024
        expected_chunks = (2 * 1024 * 1024) // chunk_size  # 32 full chunks
        
        assert len(enqueued) == expected_chunks
        
        # Verify all chunks except last are exactly chunk_size
        for i in range(expected_chunks - 1):
            assert len(enqueued[i][0]) == chunk_size
        
        # Last chunk should have newline
        assert enqueued[-1][0].endswith("\n")


class TestDrainBarrier:
    """Test output drain barrier mechanism."""
    
    @pytest.mark.asyncio
    async def test_drain_outputs_barrier(self):
        """Test that drain_outputs waits for all pending outputs."""
        transport = AsyncMock(spec=MessageTransport)
        loop = asyncio.get_event_loop()
        namespace: Dict[str, Any] = {}
        
        executor = ThreadedExecutor(
            transport, 
            "test-exec-1",
            namespace,
            loop,
            drain_timeout_ms=5000
        )
        
        # Start pump
        await executor.start_output_pump()
        
        # Queue some outputs
        executor._enqueue_from_thread("Line 1\n", StreamType.STDOUT)
        executor._enqueue_from_thread("Line 2\n", StreamType.STDOUT)
        executor._enqueue_from_thread("Line 3\n", StreamType.STDOUT)
        
        # Drain should complete after all outputs sent
        await executor.drain_outputs(timeout=2.0)
        
        # Verify all messages were sent
        assert transport.send_message.call_count == 3
        
        # Cleanup
        executor.shutdown_pump()
        if executor._pump_task:
            await asyncio.wait_for(executor._pump_task, timeout=1.0)
    
    @pytest.mark.asyncio
    async def test_drain_timeout_handling(self):
        """Test that drain timeout is properly reported."""
        transport = AsyncMock(spec=MessageTransport)
        
        # Make send_message slow to trigger timeout
        async def slow_send(msg):
            await asyncio.sleep(0.5)
        transport.send_message = slow_send
        
        loop = asyncio.get_event_loop()
        namespace: Dict[str, Any] = {}
        
        executor = ThreadedExecutor(
            transport,
            "test-exec-2", 
            namespace,
            loop,
            drain_timeout_ms=100  # Very short timeout
        )
        
        await executor.start_output_pump()
        
        # Queue output
        executor._enqueue_from_thread("Slow output\n", StreamType.STDOUT)
        
        # Should timeout
        from src.subprocess.executor import OutputDrainTimeout
        with pytest.raises(OutputDrainTimeout) as exc_info:
            await executor.drain_outputs(timeout=0.1)
        
        assert "drain_outputs timeout" in str(exc_info.value)
        
        # Cleanup
        executor.shutdown_pump()
        if executor._pump_task:
            try:
                await asyncio.wait_for(executor._pump_task, timeout=1.0)
            except asyncio.TimeoutError:
                pass


class TestSimulatedRealUsage:
    """Test simulated real-world usage patterns."""
    
    def test_simulated_tqdm(self):
        """Simulate tqdm-style progress bar output."""
        executor = Mock()
        executor._line_chunk_size = 64 * 1024
        enqueued = []
        executor._enqueue_from_thread = lambda data, stream: enqueued.append(data)
        
        output = ThreadSafeOutput(executor, StreamType.STDOUT)
        
        # Simulate tqdm progress bar
        total = 100
        for i in range(0, total + 1, 10):
            bar_length = i // 2
            bar = "█" * bar_length + "░" * (50 - bar_length)
            output.write(f"{bar} {i}%\r")
            
        output.write("\n")  # Final newline after completion
        
        # Should have 11 progress updates + 1 newline
        assert len(enqueued) == 12
        
        # Each update should end with \r except the last
        for i in range(11):
            assert enqueued[i].endswith("\r")
        assert enqueued[-1] == "\n"
    
    def test_mixed_output_patterns(self):
        """Test mixed output patterns from different libraries."""
        executor = Mock()
        executor._line_chunk_size = 64 * 1024
        enqueued = []
        executor._enqueue_from_thread = lambda data, stream: enqueued.append((data, stream))
        
        stdout = ThreadSafeOutput(executor, StreamType.STDOUT)
        stderr = ThreadSafeOutput(executor, StreamType.STDERR)
        
        # Normal print
        stdout.write("Starting process...\n")
        
        # Progress bar on stderr (like some libraries do)
        for i in range(3):
            stderr.write(f"Progress: {i*33}%\r")
        stderr.write("Progress: 100%\n")
        
        # More normal output
        stdout.write("Process complete.\n")
        
        # Verify correct interleaving
        assert len(enqueued) == 6
        assert enqueued[0] == ("Starting process...\n", StreamType.STDOUT)
        assert enqueued[1] == ("Progress: 0%\r", StreamType.STDERR)
        assert enqueued[2] == ("Progress: 33%\r", StreamType.STDERR)
        assert enqueued[3] == ("Progress: 66%\r", StreamType.STDERR)
        assert enqueued[4] == ("Progress: 100%\n", StreamType.STDERR)
        assert enqueued[5] == ("Process complete.\n", StreamType.STDOUT)


@pytest.mark.asyncio
async def test_sys_stdout_encoding_integration():
    """Test that sys.stdout.encoding works in actual execution."""
    transport = AsyncMock(spec=MessageTransport)
    loop = asyncio.get_event_loop()
    namespace: Dict[str, Any] = {}
    
    executor = ThreadedExecutor(
        transport,
        "test-exec-3",
        namespace, 
        loop
    )
    
    await executor.start_output_pump()
    
    # Code that checks encoding (like some libraries do)
    code = """
import sys
print(f"stdout.encoding: {sys.stdout.encoding}")
print(f"stdout.errors: {sys.stdout.errors}")
print(f"stdout.writable(): {sys.stdout.writable()}")
"""
    
    # Run in thread
    import threading
    thread = threading.Thread(
        target=executor.execute_code,
        args=(code,),
        daemon=True
    )
    thread.start()
    thread.join(timeout=2.0)
    
    # Wait for outputs
    await executor.drain_outputs(timeout=2.0)
    
    # Verify encoding was accessible
    assert not executor._error
    
    # Check that output messages were sent
    sent_outputs = []
    for call in transport.send_message.call_args_list:
        msg = call[0][0]
        if hasattr(msg, 'data'):
            sent_outputs.append(msg.data)
    
    output_text = "".join(sent_outputs)
    assert "stdout.encoding: utf-8" in output_text
    assert "stdout.errors: replace" in output_text
    assert "stdout.writable(): True" in output_text
    
    # Cleanup
    executor.shutdown_pump()
    if executor._pump_task:
        await asyncio.wait_for(executor._pump_task, timeout=1.0)


@pytest.mark.asyncio
async def test_output_before_result_long_lines():
    """End-to-end: very long line output is emitted fully before the result."""
    session = Session()
    await session.start()
    try:
        long_line_len = 100_000
        code = f"""
data = 'x' * {long_line_len}
print(data)
"done"
"""
        msg = ExecuteMessage(id=str(uuid.uuid4()), timestamp=time.time(), code=code)
        messages: list = []
        async for m in session.execute(msg):
            messages.append(m)

        # Indices for first result and last output
        out_indices = [i for i, m in enumerate(messages) if isinstance(m, OutputMessage)]
        res_indices = [i for i, m in enumerate(messages) if isinstance(m, ResultMessage)]
        assert out_indices, "Expected output messages"
        assert res_indices, "Expected a result message"
        assert max(out_indices) < min(res_indices), "Result must come after all outputs"
    finally:
        await session.shutdown()


@pytest.mark.asyncio
async def test_output_before_result_with_carriage_returns():
    """End-to-end: CR progress updates precede the result; last output has final progress string."""
    session = Session()
    await session.start()
    try:
        N = 50
        code = (
            "import sys, time\n"
            f"N = {N}\n"
            "for i in range(0, N):\n"
            "    print(\"\\rProgress \" + str(i) + \"/\" + str(N), end='', flush=True)\n"
            "    time.sleep(0.01)\n"
            "print(\"\\n\", end='')\n"
            "\"done\"\n"
        )
        msg = ExecuteMessage(id=str(uuid.uuid4()), timestamp=time.time(), code=code)
        messages: list = []
        async for m in session.execute(msg):
            messages.append(m)

        out_msgs = [m for m in messages if isinstance(m, OutputMessage)]
        res_msgs = [m for m in messages if isinstance(m, ResultMessage)]
        err_msgs = [m for m in messages if isinstance(m, ErrorMessage)]
        assert out_msgs, "Expected CR outputs"
        # If a result was produced, it must come after outputs; otherwise an error is acceptable per drain-timeout policy
        if res_msgs:
            assert messages.index(res_msgs[0]) > messages.index(out_msgs[-1])
        elif err_msgs:
            # Error must also appear after outputs (result withheld if drain fails)
            assert messages.index(err_msgs[0]) > messages.index(out_msgs[-1])
        else:
            pytest.fail("Expected either a result or error after outputs")
        # One of the output chunks should contain the final progress string (N-1)
        assert any(f"Progress {N-1}/{N}" in m.data for m in out_msgs)
    finally:
        await session.shutdown()
