"""Unit tests for framing protocol components."""

import pytest
import asyncio
import struct
from src.protocol.framing import FrameBuffer, StreamMultiplexer


@pytest.mark.unit
class TestFrameBuffer:
    """Test FrameBuffer functionality."""
    
    @pytest.mark.asyncio
    async def test_frame_buffer_creation(self):
        """Test creating a frame buffer."""
        buffer = FrameBuffer(max_frame_size=1024)
        assert buffer._max_frame_size == 1024
        assert len(buffer._buffer) == 0
        assert len(buffer._frames) == 0
    
    @pytest.mark.asyncio
    async def test_frame_buffer_append_data(self):
        """Test appending data to buffer."""
        buffer = FrameBuffer()
        
        # Create a simple frame with length prefix
        data = b"hello"
        frame = struct.pack(">I", len(data)) + data
        
        await buffer.append(frame)
        
        # Check frame was extracted
        assert len(buffer._frames) == 1
        assert buffer._frames[0] == data
    
    @pytest.mark.asyncio
    async def test_frame_buffer_get_frame(self):
        """Test getting frames from buffer."""
        buffer = FrameBuffer()
        
        # Add a complete frame
        data = b"test data"
        frame = struct.pack(">I", len(data)) + data
        await buffer.append(frame)
        
        # Get the frame
        result = await buffer.get_frame(timeout=0.1)
        assert result == data
        
        # No more frames
        result = await buffer.get_frame(timeout=0.1)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_frame_buffer_partial_frames(self):
        """Test handling partial frames."""
        buffer = FrameBuffer()
        
        data = b"complete frame"
        frame = struct.pack(">I", len(data)) + data
        
        # Send partial frame
        await buffer.append(frame[:5])
        assert len(buffer._frames) == 0  # No complete frame yet
        
        # Send rest of frame
        await buffer.append(frame[5:])
        assert len(buffer._frames) == 1
        assert buffer._frames[0] == data
    
    @pytest.mark.asyncio
    async def test_frame_buffer_overflow_protection(self):
        """Test protection against oversized frames."""
        buffer = FrameBuffer(max_frame_size=10)
        
        # Try to send oversized frame
        data = b"x" * 100
        frame = struct.pack(">I", len(data)) + data
        
        with pytest.raises(ValueError, match="Frame too large"):
            await buffer.append(frame)
        
        # Buffer should be cleared after error
        assert len(buffer._buffer) == 0


@pytest.mark.unit
class TestStreamMultiplexer:
    """Test StreamMultiplexer functionality."""
    
    @pytest.mark.asyncio
    async def test_multiplexer_creation(self):
        """Test creating a stream multiplexer."""
        mux = StreamMultiplexer()
        assert len(mux._streams) == 0
    
    @pytest.mark.asyncio
    async def test_multiplexer_create_stream(self):
        """Test creating logical streams."""
        mux = StreamMultiplexer()
        
        # Create a stream
        stream1 = await mux.create_stream("stream1")
        assert isinstance(stream1, asyncio.Queue)
        assert "stream1" in mux._streams
        
        # Create another stream
        stream2 = await mux.create_stream("stream2")
        assert isinstance(stream2, asyncio.Queue)
        assert "stream2" in mux._streams
        assert len(mux._streams) == 2
    
    @pytest.mark.asyncio
    async def test_multiplexer_send_to_stream(self):
        """Test sending data to specific streams."""
        mux = StreamMultiplexer()
        
        # Create streams
        stream1 = await mux.create_stream("stream1")
        stream2 = await mux.create_stream("stream2")
        
        # Send data to streams
        await mux.send_to_stream("stream1", b"data1")
        await mux.send_to_stream("stream2", b"data2")
        
        # Verify data received
        data1 = await asyncio.wait_for(stream1.get(), timeout=0.1)
        assert data1 == b"data1"
        
        data2 = await asyncio.wait_for(stream2.get(), timeout=0.1)
        assert data2 == b"data2"
    
    @pytest.mark.asyncio
    async def test_multiplexer_close_stream(self):
        """Test closing a stream."""
        mux = StreamMultiplexer()
        
        # Create and close stream
        stream = await mux.create_stream("test")
        await mux.close_stream("test")
        
        assert "test" not in mux._streams