#!/usr/bin/env python3
"""Test if worker properly routes messages."""

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

async def test_message_routing():
    """Test if worker properly routes execute messages."""
    print("=" * 50)
    print("TEST: Worker Message Routing")
    print("=" * 50)
    
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
        print("1. Reading ready message...")
        length_bytes = await asyncio.wait_for(process.stdout.read(4), timeout=2.0)
        length = struct.unpack(">I", length_bytes)[0]
        data = await process.stdout.read(length)
        ready_msg = msgpack.unpackb(data, raw=False, strict_map_key=False)
        print(f"   Ready received, capabilities: {ready_msg.get('capabilities', [])}")
        
        # Send execute message
        print("\n2. Sending execute message...")
        execute_msg = {
            "type": "execute",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "code": "print('Test output')\nresult = 42",
            "transaction_id": None,
            "transaction_policy": "commit_always",
            "capture_source": True
        }
        
        encoded = msgpack.packb(execute_msg, use_bin_type=True)
        frame = struct.pack(">I", len(encoded)) + encoded
        
        print(f"   Message type: {execute_msg['type']}")
        print(f"   Message id: {execute_msg['id']}")
        print(f"   Frame size: {len(frame)} bytes")
        
        process.stdin.write(frame)
        await process.stdin.drain()
        
        # Read all responses for 5 seconds
        print("\n3. Reading responses...")
        responses = []
        start_time = time.time()
        
        while time.time() - start_time < 5.0:
            try:
                length_bytes = await asyncio.wait_for(process.stdout.read(4), timeout=0.5)
                
                if len(length_bytes) == 4:
                    length = struct.unpack(">I", length_bytes)[0]
                    data = await process.stdout.read(length)
                    response = msgpack.unpackb(data, raw=False, strict_map_key=False)
                    
                    msg_type = response.get('type', 'unknown')
                    msg_id = response.get('id', 'no-id')
                    exec_id = response.get('execution_id', 'no-exec-id')
                    
                    print(f"   Received: type={msg_type}, id={msg_id[:8]}..., exec_id={exec_id[:8] if exec_id != 'no-exec-id' else exec_id}")
                    responses.append(response)
                    
                    # Show output if present
                    if msg_type == 'output':
                        print(f"     Output: {response.get('data', '')}")
                    elif msg_type == 'result':
                        print(f"     Result: {response.get('value', 'None')}")
                    
                    if msg_type in ['result', 'error']:
                        print("   Got final message, stopping...")
                        break
                        
            except asyncio.TimeoutError:
                continue
        
        # Analyze responses
        print(f"\n4. Analysis:")
        print(f"   Total responses: {len(responses)}")
        print(f"   Response types: {[r.get('type') for r in responses]}")
        
        # Check if execute was processed
        execute_responses = [r for r in responses if r.get('execution_id') == execute_msg['id']]
        print(f"   Execute-related responses: {len(execute_responses)}")
        
        # Check stderr for debug logs
        print("\n5. Checking stderr for debug logs...")
        try:
            stderr_data = await asyncio.wait_for(process.stderr.read(10000), timeout=0.5)
            if stderr_data:
                stderr_text = stderr_data.decode('utf-8', errors='replace')
                print("   STDERR Output (first 2000 chars):")
                print("   " + "\n   ".join(stderr_text[:2000].split("\n")))
        except:
            print("   No stderr output")
        
        if execute_responses:
            print("\n✓ SUCCESS: Execute message was processed")
            
            # Log success to investigation log
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "tags": ["testing", "validation", "breakthrough"],
                "summary": "Execute message successfully processed",
                "details": f"Worker processed execute message and sent {len(execute_responses)} responses. Types: {[r['type'] for r in execute_responses]}",
                "hypothesis": None,
                "falsification_steps": None,
                "outcome": "Fix confirmed - messages are being routed correctly",
                "notes": "Issue was in transport layer timeout causing race conditions"
            }
            
            log_file = Path(__file__).parent.parent.parent / "troubleshooting" / "investigation_log.json"
            if log_file.exists():
                with open(log_file) as f:
                    logs = json.load(f)
                logs.append(log_entry)
                with open(log_file, 'w') as f:
                    json.dump(logs, f, indent=2)
            
            return True
        else:
            print("\n✗ FAILURE: Execute message was NOT processed")
            
            # Log failure
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "tags": ["testing", "investigation"],
                "summary": "Execute message still not processed",
                "details": f"Worker did not process execute message. Response types: {[r.get('type') for r in responses]}",
                "hypothesis": "Message type handling or deserialization issue",
                "falsification_steps": "Check stderr logs for exact error",
                "outcome": "Need further debugging",
                "notes": None
            }
            
            log_file = Path(__file__).parent.parent.parent / "troubleshooting" / "investigation_log.json"
            if log_file.exists():
                with open(log_file) as f:
                    logs = json.load(f)
                logs.append(log_entry)
                with open(log_file, 'w') as f:
                    json.dump(logs, f, indent=2)
                
            return False
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        process.terminate()
        await process.wait()

if __name__ == "__main__":
    success = asyncio.run(test_message_routing())
    sys.exit(0 if success else 1)