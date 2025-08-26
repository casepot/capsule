from __future__ import annotations

import asyncio
import struct
from collections import deque
from typing import Optional

import structlog

logger = structlog.get_logger()


class FrameBuffer:
    """Efficient frame buffer with zero-copy operations where possible."""
    
    def __init__(self, max_frame_size: int = 10 * 1024 * 1024) -> None:
        self._buffer = bytearray()
        self._max_frame_size = max_frame_size
        self._frames: deque[bytes] = deque()
        self._lock = asyncio.Lock()
        
    async def append(self, data: bytes) -> None:
        """Append data to the buffer and extract complete frames."""
        async with self._lock:
            self._buffer.extend(data)
            await self._extract_frames()
    
    async def _extract_frames(self) -> None:
        """Extract complete frames from the buffer."""
        while len(self._buffer) >= 4:
            # Read length prefix
            length = struct.unpack(">I", self._buffer[:4])[0]
            
            # Validate frame size
            if length > self._max_frame_size:
                logger.error("Frame too large", size=length, max_size=self._max_frame_size)
                # Clear buffer to recover from protocol error
                self._buffer.clear()
                raise ValueError(f"Frame too large: {length} bytes")
            
            # Check if we have complete frame
            if len(self._buffer) < 4 + length:
                break
            
            # Extract frame
            frame = bytes(self._buffer[4:4 + length])
            del self._buffer[:4 + length]
            
            self._frames.append(frame)
    
    async def get_frame(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Get the next complete frame if available.
        
        Args:
            timeout: Optional timeout in seconds
            
        Returns:
            Frame data or None if no frame available
        """
        deadline = asyncio.get_event_loop().time() + timeout if timeout else None
        
        while True:
            async with self._lock:
                if self._frames:
                    return self._frames.popleft()
            
            if deadline:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    return None
                await asyncio.sleep(min(remaining, 0.01))
            else:
                return None
    
    def has_frame(self) -> bool:
        """Check if a complete frame is available."""
        return len(self._frames) > 0
    
    def clear(self) -> None:
        """Clear all buffered data."""
        self._buffer.clear()
        self._frames.clear()


class StreamMultiplexer:
    """Multiplexes multiple logical streams over a single transport."""
    
    def __init__(self) -> None:
        self._streams: dict[str, asyncio.Queue[bytes]] = {}
        self._lock = asyncio.Lock()
        
    async def create_stream(self, stream_id: str) -> asyncio.Queue[bytes]:
        """Create a new logical stream.
        
        Args:
            stream_id: Unique stream identifier
            
        Returns:
            Queue for receiving data on this stream
        """
        async with self._lock:
            if stream_id in self._streams:
                raise ValueError(f"Stream {stream_id} already exists")
            
            queue: asyncio.Queue[bytes] = asyncio.Queue()
            self._streams[stream_id] = queue
            return queue
    
    async def send_to_stream(self, stream_id: str, data: bytes) -> None:
        """Send data to a specific stream.
        
        Args:
            stream_id: Stream identifier
            data: Data to send
        """
        async with self._lock:
            if stream_id not in self._streams:
                logger.warning("Stream not found", stream_id=stream_id)
                return
            
            await self._streams[stream_id].put(data)
    
    async def close_stream(self, stream_id: str) -> None:
        """Close a logical stream.
        
        Args:
            stream_id: Stream identifier
        """
        async with self._lock:
            if stream_id in self._streams:
                # Send sentinel to indicate stream closure
                await self._streams[stream_id].put(b"")
                del self._streams[stream_id]
    
    async def close_all(self) -> None:
        """Close all streams."""
        async with self._lock:
            for stream_id in list(self._streams.keys()):
                await self._streams[stream_id].put(b"")
            self._streams.clear()


class RateLimiter:
    """Rate limiter for protocol messages."""
    
    def __init__(
        self,
        max_messages_per_second: int = 1000,
        burst_size: int = 100,
    ) -> None:
        self._max_rate = max_messages_per_second
        self._burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_update = asyncio.get_event_loop().time()
        self._lock = asyncio.Lock()
        
    async def acquire(self) -> None:
        """Acquire permission to send a message.
        
        This will block if rate limit is exceeded.
        """
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_update
            self._last_update = now
            
            # Replenish tokens
            self._tokens = min(
                self._burst_size,
                self._tokens + elapsed * self._max_rate
            )
            
            # Wait if no tokens available
            while self._tokens < 1:
                await asyncio.sleep(1.0 / self._max_rate)
                now = asyncio.get_event_loop().time()
                elapsed = now - self._last_update
                self._last_update = now
                self._tokens = min(
                    self._burst_size,
                    self._tokens + elapsed * self._max_rate
                )
            
            # Consume token
            self._tokens -= 1
    
    def try_acquire(self) -> bool:
        """Try to acquire permission without blocking.
        
        Returns:
            True if acquired, False if rate limit exceeded
        """
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_update
        self._last_update = now
        
        # Replenish tokens
        self._tokens = min(
            self._burst_size,
            self._tokens + elapsed * self._max_rate
        )
        
        # Check if token available
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        
        return False