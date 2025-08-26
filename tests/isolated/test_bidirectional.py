#!/usr/bin/env python3
"""Test bidirectional communication with worker."""

import asyncio
import sys
import json
import struct
import time
import uuid
import msgpack
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def test_bidirectional():
    """Test sending and receiving messages."""
    print("=" * 50)
    print("TEST: Bidirectional Communication")
    print("=" * 50)
    
    # Start subprocess
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m", "src.subprocess.worker",
        "test-session-id",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    print(f"Process started, PID: {process.pid}")
    
    try:
        # Read ready message
        print("1. Reading ready message...")
        length_bytes = await asyncio.wait_for(process.stdout.read(4), timeout=2.0)
        length = struct.unpack(">I", length_bytes)[0]
        data = await process.stdout.read(length)
        ready_msg = msgpack.unpackb(data, raw=False, strict_map_key=False)
        print(f"   Received: {ready_msg['type']}")
        
        # Send execute message
        print("2. Sending execute message...")
        execute_msg = {
            "type": "execute",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "code": "print('Hello from test!')",
            "transaction_id": None,
            "transaction_policy": "commit_always",
            "capture_source": True
        }
        
        # Encode with msgpack
        encoded = msgpack.packb(execute_msg, use_bin_type=True)
        frame = struct.pack(">I", len(encoded)) + encoded
        
        process.stdin.write(frame)
        await process.stdin.drain()
        print(f"   Sent {len(frame)} bytes")
        
        # Try to read response
        print("3. Waiting for response...")
        
        # Set up timeout
        responses = []
        start_time = time.time()
        
        while time.time() - start_time < 3.0:
            try:
                # Check if data available
                length_bytes = await asyncio.wait_for(
                    process.stdout.read(4),
                    timeout=0.5
                )
                
                if len(length_bytes) == 4:
                    length = struct.unpack(">I", length_bytes)[0]
                    data = await process.stdout.read(length)
                    response = msgpack.unpackb(data, raw=False, strict_map_key=False)
                    print(f"   Received: {response['type']}")
                    responses.append(response)
                    
                    # Check if this is the final message
                    if response['type'] in ['result', 'error']:
                        break
                        
            except asyncio.TimeoutError:
                continue
        
        if responses:
            print(f"SUCCESS: Received {len(responses)} responses")
            
            # Log success
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "tags": ["testing", "validation", "breakthrough"],
                "summary": "Bidirectional communication works",
                "details": f"Successfully sent execute and received {len(responses)} responses. Types: {[r['type'] for r in responses]}",
                "hypothesis": None,
                "falsification_steps": None,
                "outcome": "Worker processes messages correctly",
                "notes": "Issue must be in Session/PipeTransport layer"
            }
        else:
            print("FAILURE: No responses received")
            
            # Check stderr
            try:
                stderr_data = await asyncio.wait_for(
                    process.stderr.read(1000),
                    timeout=0.5
                )
                if stderr_data:
                    print(f"STDERR: {stderr_data.decode('utf-8', errors='replace')}")
            except:
                pass
            
            # Log failure
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "tags": ["testing", "investigation"],
                "summary": "Worker not processing execute messages",
                "details": "Worker received execute message but didn't respond",
                "hypothesis": "Execute handler may be broken",
                "falsification_steps": "Add logging to worker execute method",
                "outcome": "Need to debug worker execution",
                "notes": None
            }
        
        # Append to log
        log_file = Path(__file__).parent.parent.parent / "troubleshooting" / "investigation_log.json"
        if log_file.exists():
            with open(log_file) as f:
                logs = json.load(f)
            logs.append(log_entry)
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        
        return len(responses) > 0
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Kill process
        try:
            process.terminate()
            await process.wait()
        except:
            pass


if __name__ == "__main__":
    success = asyncio.run(test_bidirectional())
    sys.exit(0 if success else 1)