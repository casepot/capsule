"""
Direct test of frame communication between processes
Tests if MessageTransport/FrameReader work correctly
"""
import asyncio
import sys
import json
import struct
import time
import uuid

async def test_direct_frames():
    """Test frame communication without Session/Pool layers"""
    print("\n=== Testing Direct Frame Communication ===\n")
    
    # Start worker subprocess
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "src.subprocess.worker", "test-session",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    print(f"Worker process started: PID {process.pid}")
    
    # Create simple frame writer
    def write_frame(data_bytes):
        """Write a frame with length prefix"""
        frame = struct.pack(">I", len(data_bytes)) + data_bytes
        process.stdin.write(frame)
        return asyncio.create_task(process.stdin.drain())
    
    # Create simple frame reader with debug
    async def read_frame_with_timeout(timeout=5.0):
        """Read a frame with timeout and debugging"""
        try:
            # Read length prefix
            print(f"  Waiting for 4-byte length prefix...")
            length_bytes = await asyncio.wait_for(
                process.stdout.readexactly(4), 
                timeout=timeout
            )
            length = struct.unpack(">I", length_bytes)[0]
            print(f"  Got length: {length}")
            
            # Read data
            print(f"  Waiting for {length} data bytes...")
            data = await asyncio.wait_for(
                process.stdout.readexactly(length),
                timeout=timeout
            )
            print(f"  Got data, decoding...")
            
            # Decode msgpack
            import msgpack
            msg = msgpack.unpackb(data, raw=False, strict_map_key=False)
            print(f"  Decoded message type: {msg.get('type')}")
            return msg
            
        except asyncio.TimeoutError:
            print(f"  TIMEOUT waiting for frame!")
            return None
        except Exception as e:
            print(f"  ERROR reading frame: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # Wait for ready message
    print("\n1. Waiting for READY message...")
    msg = await read_frame_with_timeout()
    if msg and msg.get('type') == 'ready':
        print(f"✓ Got READY: session={msg.get('session_id')}")
    else:
        print(f"✗ Expected ready, got: {msg}")
        process.kill()
        return False
    
    # Send execute message
    print("\n2. Sending EXECUTE message...")
    exec_msg = {
        'type': 'execute',
        'id': str(uuid.uuid4()),
        'timestamp': time.time(),
        'code': 'print("Hello from worker"); result = 42',
        'capture_source': False,
    }
    
    import msgpack
    data = msgpack.packb(exec_msg, use_bin_type=True)
    await write_frame(data)
    print(f"  Sent execute: {len(data)} bytes")
    
    # Read responses
    print("\n3. Reading responses...")
    responses = []
    for i in range(10):  # Try to read up to 10 messages
        print(f"\n  Attempt {i+1}:")
        msg = await read_frame_with_timeout(timeout=1.0)
        if msg:
            responses.append(msg['type'])
            print(f"  → Received: {msg['type']}")
            if msg['type'] in ['result', 'error']:
                print(f"  → Execution complete!")
                break
        else:
            print(f"  → No more messages")
            break
    
    print(f"\n4. Summary:")
    print(f"  Received {len(responses)} messages: {responses}")
    
    # Kill process
    process.kill()
    await process.wait()
    
    return 'result' in responses or 'error' in responses

if __name__ == "__main__":
    success = asyncio.run(test_direct_frames())
    print(f"\n{'✓ SUCCESS' if success else '✗ FAILED'}")
    sys.exit(0 if success else 1)
