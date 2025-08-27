"""Integration tests for subprocess worker."""

import pytest
import asyncio
import sys
import struct
import msgpack
from pathlib import Path
from src.protocol.messages import MessageType, parse_message
from tests.fixtures.messages import MessageFactory


@pytest.mark.integration
class TestWorkerCommunication:
    """Test worker subprocess communication."""
    
    @pytest.mark.asyncio
    async def test_worker_startup(self):
        """Test that worker subprocess starts and sends ready message."""
        # Start subprocess directly
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m", "src.subprocess.worker",
            "test-session-id",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            # Read ready message
            length_bytes = await asyncio.wait_for(
                process.stdout.read(4),
                timeout=2.0
            )
            length = struct.unpack(">I", length_bytes)[0]
            
            data = await asyncio.wait_for(
                process.stdout.read(length),
                timeout=2.0
            )
            
            message = msgpack.unpackb(data, raw=False, strict_map_key=False)
            assert message["type"] == "ready"
            assert "capabilities" in message
            
        finally:
            process.terminate()
            await process.wait()
    
    @pytest.mark.asyncio
    async def test_worker_execute_message(self):
        """Test worker processes execute messages."""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m", "src.subprocess.worker",
            "test-session-id",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            # Wait for ready message
            length_bytes = await process.stdout.read(4)
            length = struct.unpack(">I", length_bytes)[0]
            await process.stdout.read(length)  # Discard ready message
            
            # Send execute message
            execute_msg = {
                "type": "execute",
                "id": "test-exec",
                "timestamp": 0,
                "code": "print('test'); 42"
            }
            
            msg_data = msgpack.packb(execute_msg)
            length_bytes = struct.pack(">I", len(msg_data))
            process.stdin.write(length_bytes + msg_data)
            await process.stdin.drain()
            
            # Read responses
            responses = []
            timeout = 2.0
            start = asyncio.get_event_loop().time()
            
            while asyncio.get_event_loop().time() - start < timeout:
                try:
                    length_bytes = await asyncio.wait_for(
                        process.stdout.read(4),
                        timeout=0.5
                    )
                    length = struct.unpack(">I", length_bytes)[0]
                    data = await process.stdout.read(length)
                    message = msgpack.unpackb(data, raw=False, strict_map_key=False)
                    responses.append(message)
                    
                    if message["type"] in ["result", "error"]:
                        break
                except asyncio.TimeoutError:
                    break
            
            # Verify we got output and result
            types = [r["type"] for r in responses]
            assert "output" in types or "result" in types
            
        finally:
            process.terminate()
            await process.wait()
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_worker_message_routing(self):
        """Test worker properly routes different message types."""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m", "src.subprocess.worker",
            "test-session-id",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            # Wait for ready
            length_bytes = await process.stdout.read(4)
            length = struct.unpack(">I", length_bytes)[0]
            await process.stdout.read(length)
            
            # Test heartbeat message
            heartbeat_msg = {
                "type": "heartbeat",
                "id": "test-hb",
                "timestamp": 0
            }
            
            msg_data = msgpack.packb(heartbeat_msg)
            length_bytes = struct.pack(">I", len(msg_data))
            process.stdin.write(length_bytes + msg_data)
            await process.stdin.drain()
            
            # Should get heartbeat response
            length_bytes = await asyncio.wait_for(
                process.stdout.read(4),
                timeout=1.0
            )
            length = struct.unpack(">I", length_bytes)[0]
            data = await process.stdout.read(length)
            response = msgpack.unpackb(data, raw=False, strict_map_key=False)
            
            assert response["type"] == "heartbeat"
            
        finally:
            process.terminate()
            await process.wait()