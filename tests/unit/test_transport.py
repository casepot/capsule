"""Unit tests for transport layer."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.protocol.transport import MessageTransport, FrameReader, FrameWriter
from src.protocol.messages import HeartbeatMessage


@pytest.mark.unit
class TestFrameReader:
    """Test FrameReader functionality."""
    
    @pytest.mark.asyncio
    async def test_read_frame_with_valid_data(self):
        """Test reading a complete frame."""
        reader = AsyncMock()
        # Return complete frame data in one read
        reader.read = AsyncMock(side_effect=[
            b"\x00\x00\x00\x05hello",  # Length prefix + data
            b"",  # EOF on next read
        ])
        
        frame_reader = FrameReader(reader)
        await frame_reader.start()  # Start the background task
        
        try:
            frame = await frame_reader.read_frame(timeout=1.0)
            assert frame == b"hello"
        finally:
            await frame_reader.stop()
    
    @pytest.mark.asyncio
    async def test_read_frame_timeout(self):
        """Test frame read timeout."""
        reader = AsyncMock()
        # Block forever to trigger timeout in read_frame
        async def block_forever(*args, **kwargs):
            await asyncio.sleep(100)
        reader.read = AsyncMock(side_effect=block_forever)
        
        frame_reader = FrameReader(reader)
        await frame_reader.start()
        
        try:
            with pytest.raises(asyncio.TimeoutError):
                await frame_reader.read_frame(timeout=0.1)
        finally:
            await frame_reader.stop()
    
    @pytest.mark.asyncio
    async def test_read_frame_eof(self):
        """Test handling EOF during frame read."""
        reader = AsyncMock()
        reader.read = AsyncMock(return_value=b"")  # EOF immediately
        
        frame_reader = FrameReader(reader)
        await frame_reader.start()
        
        try:
            # Should raise ProtocolError when connection closes
            from src.protocol.transport import ProtocolError
            with pytest.raises(ProtocolError):
                await frame_reader.read_frame(timeout=1.0)
        finally:
            await frame_reader.stop()


@pytest.mark.unit
class TestFrameWriter:
    """Test FrameWriter functionality."""
    
    @pytest.mark.asyncio
    async def test_write_frame(self):
        """Test writing a frame with length prefix."""
        # Create writer mock with sync write() and async drain()
        writer = MagicMock()
        writer.write = Mock()  # Sync method
        writer.drain = AsyncMock()  # Async method
        
        frame_writer = FrameWriter(writer)
        await frame_writer.write_frame(b"test")
        
        # Check frame was written as single call
        writer.write.assert_called_once()
        written_data = writer.write.call_args[0][0]
        # Should be length prefix + data
        assert written_data == b"\x00\x00\x00\x04test"
        # Check drain was called
        writer.drain.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_write_empty_frame(self):
        """Test writing an empty frame."""
        writer = MagicMock()
        writer.write = Mock()  # Sync method
        writer.drain = AsyncMock()  # Async method
        
        frame_writer = FrameWriter(writer)
        await frame_writer.write_frame(b"")
        
        writer.write.assert_called_once_with(b"\x00\x00\x00\x00")
        writer.drain.assert_called_once()


@pytest.mark.unit
class TestMessageTransport:
    """Test MessageTransport functionality."""
    
    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending a message."""
        reader = AsyncMock()
        reader.read = AsyncMock(return_value=b"")  # Mock for FrameReader
        
        writer = MagicMock()
        writer.write = Mock()  # Sync
        writer.drain = AsyncMock()  # Async
        writer.close = Mock()  # Sync
        writer.wait_closed = AsyncMock()  # Async
        
        transport = MessageTransport(reader, writer)
        await transport.start()
        
        try:
            # Send a message
            msg = HeartbeatMessage(
                id="test",
                timestamp=123.456,
                memory_usage=1024,
                cpu_percent=50.0,
                namespace_size=10
            )
            await transport.send_message(msg)
            
            # Check message was serialized and sent
            writer.write.assert_called_once()
            writer.drain.assert_called_once()
        finally:
            await transport.close()
    
    @pytest.mark.asyncio
    async def test_receive_message(self):
        """Test receiving a message."""
        import msgpack
        import struct
        
        # Create heartbeat message data
        heartbeat_data = msgpack.packb({
            "type": "heartbeat",
            "id": "test",
            "timestamp": 123.456,
            "memory_usage": 1024,
            "cpu_percent": 50.0,
            "namespace_size": 10
        })
        
        # Create complete frame with proper length prefix
        frame = struct.pack(">I", len(heartbeat_data)) + heartbeat_data
        
        reader = AsyncMock()
        reader.read = AsyncMock(side_effect=[
            frame,  # Return complete frame at once
            b"",  # EOF on next read
        ])
        
        writer = MagicMock()
        writer.write = Mock()  # Sync
        writer.drain = AsyncMock()  # Async
        writer.close = Mock()  # Sync
        writer.wait_closed = AsyncMock()  # Async
        
        transport = MessageTransport(reader, writer)
        await transport.start()
        
        try:
            # Receive message - note the method is receive_message not receive
            msg = await transport.receive_message(timeout=1.0)
            assert msg is not None
            from src.protocol.messages import MessageType
            assert msg.type == MessageType.HEARTBEAT
            assert msg.id == "test"
        finally:
            await transport.close()
    
    @pytest.mark.asyncio
    async def test_close_transport(self):
        """Test closing the transport."""
        reader = AsyncMock()
        reader.read = AsyncMock(return_value=b"")  # Mock for FrameReader background task
        
        writer = MagicMock()
        writer.close = Mock()  # Sync
        writer.wait_closed = AsyncMock()  # Async
        writer.write = Mock()
        writer.drain = AsyncMock()
        
        transport = MessageTransport(reader, writer)
        await transport.start()
        await transport.close()
        
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()