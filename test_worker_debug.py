#!/usr/bin/env python3
"""Debug test to see what's happening with the worker."""

import asyncio
import sys
import subprocess
import json
import msgpack
import uuid
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.protocol.messages import ExecuteMessage


async def test_worker_directly():
    """Test worker directly to see message handling."""
    print("Starting worker subprocess...")
    
    # Start worker process
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "src.subprocess.worker", "test-session",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=Path(__file__).parent
    )
    
    try:
        # Wait for ready message
        print("Waiting for ready message...")
        
        # Read length prefix
        data = await proc.stdout.read(4)
        length = int.from_bytes(data, 'big')
        print(f"Ready message length: {length}")
        
        # Read message
        data = await proc.stdout.read(length)
        ready = msgpack.unpackb(data, raw=False)
        print(f"Ready message type: {ready['type']}")
        
        # Send execute message
        msg = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code='print("test")'
        )
        
        msg_dict = msg.model_dump(mode="json")
        print(f"Sending execute with type: {msg_dict['type']} (type: {type(msg_dict['type'])})")
        
        data = msgpack.packb(msg_dict, use_bin_type=True)
        length_bytes = len(data).to_bytes(4, 'big')
        
        proc.stdin.write(length_bytes + data)
        await proc.stdin.drain()
        
        # Read responses
        print("\nWaiting for responses...")
        for _ in range(10):  # Try to read up to 10 messages
            try:
                # Read with timeout
                data = await asyncio.wait_for(proc.stdout.read(4), timeout=0.5)
                if not data:
                    break
                    
                length = int.from_bytes(data, 'big')
                data = await proc.stdout.read(length)
                response = msgpack.unpackb(data, raw=False)
                print(f"Response type: {response['type']}")
                
                if response['type'] == 'result':
                    print("Got result, execution complete")
                    break
                    
            except asyncio.TimeoutError:
                print("Timeout waiting for response")
                break
        
        # Check stderr for worker logs
        print("\nWorker stderr output:")
        try:
            stderr_data = await asyncio.wait_for(proc.stderr.read(10000), timeout=0.5)
            print(stderr_data.decode('utf-8', errors='replace'))
        except asyncio.TimeoutError:
            print("(no stderr output)")
        
    finally:
        proc.terminate()
        await proc.wait()
        print("\nWorker terminated")


if __name__ == "__main__":
    asyncio.run(test_worker_directly())