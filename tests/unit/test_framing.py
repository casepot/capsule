"""Unit tests for protocol framing components."""

import pytest
import asyncio
from src.protocol.framing import FrameBuffer, StreamMultiplexer, RateLimiter


@pytest.mark.unit
class TestFrameBuffer:
    """Test FrameBuffer functionality."""
    
    def test_frame_buffer_creation(self):
        """Test creating a frame buffer."""
        buffer = FrameBuffer(max_size=1024)
        assert buffer.max_size == 1024
        assert buffer.size == 0
    
    def test_frame_buffer_add_data(self):
        """Test adding data to frame buffer."""
        buffer = FrameBuffer(max_size=1024)
        buffer.add(b"hello")
        assert buffer.size == 5
        assert buffer.has_complete_frame() is False
    
    def test_frame_buffer_complete_frame(self):
        """Test detecting complete frame."""
        buffer = FrameBuffer(max_size=1024)
        # Add length prefix (5 bytes)
        buffer.add(b"\x00\x00\x00\x05")
        assert buffer.has_complete_frame() is False
        # Add frame data
        buffer.add(b"hello")
        assert buffer.has_complete_frame() is True
    
    def test_frame_buffer_extract_frame(self):
        """Test extracting a complete frame."""
        buffer = FrameBuffer(max_size=1024)
        buffer.add(b"\x00\x00\x00\x05hello")
        frame = buffer.extract_frame()
        assert frame == b"hello"
        assert buffer.size == 0
    
    def test_frame_buffer_overflow_protection(self):
        """Test buffer overflow protection."""
        buffer = FrameBuffer(max_size=10)
        with pytest.raises(ValueError):
            buffer.add(b"x" * 20)


@pytest.mark.unit
class TestStreamMultiplexer:
    """Test StreamMultiplexer functionality."""
    
    def test_multiplexer_creation(self):
        """Test creating a stream multiplexer."""
        mux = StreamMultiplexer()
        assert mux.stream_count == 0
    
    def test_multiplexer_add_stream(self):
        """Test adding streams to multiplexer."""
        mux = StreamMultiplexer()
        stream_id = mux.add_stream("stdout")
        assert stream_id is not None
        assert mux.stream_count == 1
    
    def test_multiplexer_multiplex_data(self):
        """Test multiplexing data with stream ID."""
        mux = StreamMultiplexer()
        stdout_id = mux.add_stream("stdout")
        stderr_id = mux.add_stream("stderr")
        
        stdout_frame = mux.multiplex(stdout_id, b"output")
        stderr_frame = mux.multiplex(stderr_id, b"error")
        
        assert stdout_frame != stderr_frame
        assert len(stdout_frame) > len(b"output")  # Has metadata
    
    def test_multiplexer_demultiplex_data(self):
        """Test demultiplexing data to get stream ID."""
        mux = StreamMultiplexer()
        stdout_id = mux.add_stream("stdout")
        
        frame = mux.multiplex(stdout_id, b"test data")
        stream, data = mux.demultiplex(frame)
        
        assert stream == stdout_id
        assert data == b"test data"