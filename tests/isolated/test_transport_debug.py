#!/usr/bin/env python3
"""Debug transport communication issues."""

import asyncio
import sys
import json
import struct
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def test_direct_subprocess():
    """Test direct subprocess communication bypassing session manager."""
    print("=" * 50)
    print("TEST: Direct Subprocess Communication")
    print("=" * 50)
    
    # Start subprocess directly
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m", "src.subprocess.worker",
        "test-session-id",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    print(f"Process started, PID: {process.pid}")
    
    # Wait a bit for initialization
    await asyncio.sleep(0.5)
    
    # Try to read ready message
    try:
        # Read from stdout with timeout
        print("Waiting for ready message...")
        
        # Try to read 4 bytes for length prefix
        length_bytes = await asyncio.wait_for(
            process.stdout.read(4),
            timeout=2.0
        )
        
        if len(length_bytes) < 4:
            print(f"ERROR: Only got {len(length_bytes)} bytes for length")
            return False
            
        length = struct.unpack(">I", length_bytes)[0]
        print(f"Message length: {length}")
        
        # Read message data
        data = await asyncio.wait_for(
            process.stdout.read(length),
            timeout=2.0
        )
        
        print(f"Received {len(data)} bytes")
        
        # Try to decode as JSON (not msgpack for debugging)
        try:
            import msgpack
            message = msgpack.unpackb(data, raw=False, strict_map_key=False)
            print(f"Decoded message: {message}")
        except Exception as e:
            print(f"Failed to decode as msgpack: {e}")
            # Try JSON
            try:
                message = json.loads(data)
                print(f"Decoded as JSON: {message}")
            except:
                print(f"Raw data: {data[:100]}")
        
        # Log finding
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tags": ["testing", "investigation", "observation"],
            "summary": "Direct subprocess communication test",
            "details": f"Subprocess started and sent data. Length={length}, decoded={bool(message) if 'message' in locals() else False}",
            "hypothesis": "Transport layer encoding/decoding mismatch",
            "falsification_steps": None,
            "outcome": "Worker sends data but may have encoding issues",
            "notes": None
        }
        
        log_file = Path(__file__).parent.parent.parent / "troubleshooting" / "investigation_log.json"
        if log_file.exists():
            with open(log_file) as f:
                logs = json.load(f)
            logs.append(log_entry)
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        
        return True
        
    except asyncio.TimeoutError:
        print("TIMEOUT: No data received from subprocess")
        
        # Check if process is still alive
        if process.returncode is None:
            print("Process is still running")
            
            # Try to read stderr
            try:
                stderr_data = await asyncio.wait_for(
                    process.stderr.read(1000),
                    timeout=0.5
                )
                if stderr_data:
                    print(f"STDERR: {stderr_data.decode('utf-8', errors='replace')}")
            except:
                print("No stderr output")
        else:
            print(f"Process exited with code: {process.returncode}")
        
        # Log failure
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tags": ["testing", "investigation", "breakthrough"],
            "summary": "Worker not sending data on stdout",
            "details": "No data received from subprocess stdout. Process may be writing elsewhere or transport not initialized",
            "hypothesis": "Worker stdout not connected properly",
            "falsification_steps": "Check worker stdout initialization",
            "outcome": "Worker transport layer broken",
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
        # Kill process
        try:
            process.terminate()
            await process.wait()
        except:
            pass


if __name__ == "__main__":
    success = asyncio.run(test_direct_subprocess())
    sys.exit(0 if success else 1)