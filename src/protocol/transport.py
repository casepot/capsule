from __future__ import annotations

import asyncio
import json
import struct
from typing import Optional

import msgpack
import structlog

from .messages import Message, parse_message

logger = structlog.get_logger()


class ProtocolError(Exception):
    """Protocol-level error."""

    pass


class FrameReader:
    """Async frame reader with proper synchronization using asyncio.Condition."""

    def __init__(self, reader: asyncio.StreamReader) -> None:
        self._reader = reader
        self._buffer = bytearray()
        self._condition = asyncio.Condition()
        self._closed = False
        self._read_task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start the background reader task."""
        if not self._read_task:
            self._read_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        """Stop the background reader task."""
        self._closed = True
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

    async def _read_loop(self) -> None:
        """Background task that continuously reads from the stream into buffer."""
        logger.debug("FrameReader._read_loop starting")
        try:
            while not self._closed:
                try:
                    logger.debug("FrameReader: waiting for data with 1.0s timeout")
                    data = await asyncio.wait_for(self._reader.read(8192), timeout=1.0)
                    if not data:
                        logger.debug("FrameReader: EOF received, closing")
                        self._closed = True
                        break

                    logger.debug(f"FrameReader: received {len(data)} bytes")
                    async with self._condition:
                        self._buffer.extend(data)
                        logger.debug(f"FrameReader: buffer now has {len(self._buffer)} bytes")
                        self._condition.notify_all()

                except asyncio.TimeoutError:
                    # This is normal - just continue
                    continue
                except Exception as e:
                    logger.error("Read loop error", error=str(e))
                    self._closed = True
                    break

        finally:
            async with self._condition:
                self._closed = True
                self._condition.notify_all()

    async def read_frame(self, timeout: Optional[float] = None) -> bytes:
        """Read a complete frame from the buffer.

        Frame format: [4 bytes length][data]

        Args:
            timeout: Optional timeout in seconds

        Returns:
            Frame data bytes

        Raises:
            ProtocolError: If connection is closed or frame is invalid
            asyncio.TimeoutError: If timeout is exceeded
        """
        logger.debug(f"read_frame called with timeout={timeout}")
        async with self._condition:
            # Wait for length prefix (4 bytes)
            logger.debug(f"Phase 1: Waiting for 4 bytes (have {len(self._buffer)})")
            try:
                await asyncio.wait_for(
                    self._condition.wait_for(lambda: len(self._buffer) >= 4 or self._closed),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.debug("Timeout waiting for length prefix")
                raise

            if self._closed and len(self._buffer) < 4:
                raise ProtocolError("Connection closed while reading frame length")

            # Read length prefix
            length = struct.unpack(">I", self._buffer[:4])[0]
            logger.debug(f"Length prefix read: {length} bytes expected")

            # Validate frame length
            if length > 10 * 1024 * 1024:  # 10MB max frame size
                raise ProtocolError(f"Frame too large: {length} bytes")

            # Wait for complete frame
            total_needed = 4 + length
            logger.debug(
                f"Phase 2: Waiting for {total_needed} bytes total (have {len(self._buffer)})"
            )
            try:
                await asyncio.wait_for(
                    self._condition.wait_for(
                        lambda: len(self._buffer) >= total_needed or self._closed
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.debug(
                    f"Timeout waiting for frame data (needed {total_needed}, have {len(self._buffer)})"
                )
                raise

            if self._closed and len(self._buffer) < total_needed:
                raise ProtocolError("Connection closed while reading frame data")

            # Extract frame
            frame = bytes(self._buffer[4:total_needed])
            del self._buffer[:total_needed]
            logger.debug(
                f"Frame extracted: {len(frame)} bytes, buffer remaining: {len(self._buffer)} bytes"
            )

            return frame


class FrameWriter:
    """Async frame writer with proper backpressure handling."""

    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self._writer = writer
        self._write_lock = asyncio.Lock()
        self._closed = False

    async def write_frame(self, data: bytes) -> None:
        """Write a frame to the stream.

        Args:
            data: Frame data to write

        Raises:
            ProtocolError: If connection is closed
        """
        if self._closed:
            raise ProtocolError("Connection closed")

        async with self._write_lock:
            # Prepare frame with length prefix
            length = len(data)
            frame = struct.pack(">I", length) + data

            # Write frame
            self._writer.write(frame)
            await self._writer.drain()

    async def close(self) -> None:
        """Close the writer."""
        if not self._closed:
            self._closed = True
            self._writer.close()
            await self._writer.wait_closed()


class MessageTransport:
    """High-level message transport using framed protocol."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        use_msgpack: bool = True,
    ) -> None:
        self._frame_reader = FrameReader(reader)
        self._frame_writer = FrameWriter(writer)
        self._use_msgpack = use_msgpack
        self._closed = False

    async def start(self) -> None:
        """Start the transport."""
        await self._frame_reader.start()

    async def send_message(self, message: Message) -> None:
        """Send a message.

        Args:
            message: Message to send

        Raises:
            ProtocolError: If transport is closed
        """
        if self._closed:
            raise ProtocolError("Transport closed")

        # Serialize message
        data_dict = message.model_dump(mode="json")

        data: bytes
        if self._use_msgpack:
            data = msgpack.packb(data_dict, use_bin_type=True)
        else:
            data = json.dumps(data_dict).encode("utf-8")

        # Send frame
        logger.debug(
            f"MessageTransport: sending frame of {len(data)} bytes for message type={message.type}"
        )
        await self._frame_writer.write_frame(data)

        logger.debug("Sent message", type=message.type, id=message.id)

    async def receive_message(self, timeout: Optional[float] = None) -> Message:
        """Receive a message.

        Args:
            timeout: Optional timeout in seconds

        Returns:
            Received message

        Raises:
            ProtocolError: If transport is closed or message is invalid
            asyncio.TimeoutError: If timeout is exceeded
        """
        if self._closed:
            raise ProtocolError("Transport closed")

        logger.debug(f"MessageTransport: waiting to receive message with timeout={timeout}")

        # Receive frame
        frame = await self._frame_reader.read_frame(timeout=timeout)
        logger.debug(f"MessageTransport: received frame of {len(frame)} bytes")

        # Deserialize message
        if self._use_msgpack:
            data_dict = msgpack.unpackb(frame, raw=False, strict_map_key=False)
        else:
            data_dict = json.loads(frame.decode("utf-8"))

        logger.debug(f"MessageTransport: deserialized message type={data_dict.get('type')}")

        # Parse message
        message = parse_message(data_dict)

        logger.debug(
            "Received message", type=message.type, id=message.id, parsed_type=type(message).__name__
        )

        return message

    async def close(self) -> None:
        """Close the transport."""
        if not self._closed:
            self._closed = True
            await self._frame_reader.stop()
            await self._frame_writer.close()


class PipeTransport:
    """Transport for subprocess communication via pipes."""

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        use_msgpack: bool = True,
    ) -> None:
        if not process.stdout or not process.stdin:
            raise ValueError("Process must have stdout and stdin pipes")

        self._process = process
        self._transport = MessageTransport(
            reader=process.stdout,
            writer=process.stdin,
            use_msgpack=use_msgpack,
        )

    async def start(self) -> None:
        """Start the transport."""
        await self._transport.start()

    async def send_message(self, message: Message) -> None:
        """Send a message to the subprocess."""
        await self._transport.send_message(message)

    async def receive_message(self, timeout: Optional[float] = None) -> Message:
        """Receive a message from the subprocess."""
        return await self._transport.receive_message(timeout=timeout)

    async def close(self) -> None:
        """Close the transport and terminate the process."""
        await self._transport.close()

        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

    def is_alive(self) -> bool:
        """Check if the subprocess is still alive."""
        return self._process.returncode is None
