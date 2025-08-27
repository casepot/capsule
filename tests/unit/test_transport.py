"""Unit tests for transport layer."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.protocol.transport import MessageTransport, FrameReader, FrameWriter
from src.protocol.messages import HeartbeatMessage


@pytest.mark.unit
class TestFrameReader:
    """Test FrameReader functionality."""
    
    @pytest.mark.asyncio
    async def test_read_frame_with_valid_data(self):
        """Test reading a complete frame."""
        reader = AsyncMock()
        reader.read.side_effect = [
            b"\x00\x00\x00\x05",  # Length prefix (5 bytes)
            b"hello",             # Frame data
        ]
        
        frame_reader = FrameReader(reader, Mock())
        frame = await frame_reader.read_frame(timeout=1.0)
        assert frame == b"hello"
    
    @pytest.mark.asyncio
    async def test_read_frame_timeout(self):
        """Test frame read timeout."""
        reader = AsyncMock()
        reader.read.side_effect = asyncio.TimeoutError
        
        frame_reader = FrameReader(reader, Mock())
        frame = await frame_reader.read_frame(timeout=0.1)
        assert frame is None
    
    @pytest.mark.asyncio
    async def test_read_frame_eof(self):
        """Test handling EOF during frame read."""
        reader = AsyncMock()
        reader.read.return_value = b""  # EOF
        
        frame_reader = FrameReader(reader, Mock())
        frame = await frame_reader.read_frame(timeout=1.0)
        assert frame is None


@pytest.mark.unit
class TestFrameWriter:
    """Test FrameWriter functionality."""
    
    @pytest.mark.asyncio
    async def test_write_frame(self):
        """Test writing a frame with length prefix."""
        writer = AsyncMock()
        
        frame_writer = FrameWriter(writer)
        await frame_writer.write_frame(b"test")
        
        # Check length prefix was written
        writer.write.assert_any_call(b"\x00\x00\x00\x04")
        # Check data was written
        writer.write.assert_any_call(b"test")
        # Check drain was called
        writer.drain.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_write_empty_frame(self):
        """Test writing an empty frame."""
        writer = AsyncMock()
        
        frame_writer = FrameWriter(writer)
        await frame_writer.write_frame(b"")
        
        writer.write.assert_any_call(b"\x00\x00\x00\x00")
        writer.write.assert_any_call(b"")


@pytest.mark.unit
class TestMessageTransport:
    """Test MessageTransport functionality."""
    
    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending a message."""
        reader = AsyncMock()
        writer = AsyncMock()
        
        transport = MessageTransport(reader, writer)
        msg = HeartbeatMessage(id="test", timestamp=0)
        
        await transport.send(msg)
        
        # Verify write and drain were called
        writer.write.assert_called()
        writer.drain.assert_called()
    
    @pytest.mark.asyncio
    async def test_receive_message(self):
        """Test receiving a message."""
        reader = AsyncMock()
        writer = AsyncMock()
        
        # Mock frame data for a heartbeat message
        frame_data = b'{"type":"heartbeat","id":"test","timestamp":0}'
        reader.read.side_effect = [
            len(frame_data).to_bytes(4, 'big'),  # Length prefix
            frame_data,                           # Message data
        ]
        
        transport = MessageTransport(reader, writer)
        transport._frame_reader = FrameReader(reader, writer)
        
        msg = await transport.receive(timeout=1.0)
        assert msg is not None
        assert msg.type == "heartbeat"
    
    @pytest.mark.asyncio
    async def test_close_transport(self):
        """Test closing the transport."""
        reader = AsyncMock()
        writer = AsyncMock()
        
        transport = MessageTransport(reader, writer)
        await transport.close()
        
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()