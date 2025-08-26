#!/usr/bin/env python3
"""Test simple code execution in a session."""

import asyncio
import sys
import time
import json
import uuid
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType


async def test_simple_execution():
    """Test executing simple code."""
    print("=" * 50)
    print("TEST: Simple Code Execution")
    print("=" * 50)
    
    start_time = time.time()
    session = Session()
    
    try:
        print(f"[{time.time()-start_time:.3f}s] Starting session...")
        await asyncio.wait_for(session.start(), timeout=5.0)
        print(f"[{time.time()-start_time:.3f}s] Session ready")
        
        # Create simple execute message
        code = "print('Hello from subprocess!')"
        message = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code=code,
        )
        
        print(f"[{time.time()-start_time:.3f}s] Executing: {code}")
        
        # Execute and collect messages
        messages_received = []
        
        try:
            execute_start = time.time()
            async for msg in session.execute(message, timeout=5.0):
                elapsed = time.time() - execute_start
                print(f"[{elapsed:.3f}s] Received: {msg.type}")
                messages_received.append(msg)
                
                if msg.type == MessageType.OUTPUT:
                    print(f"    Output: {msg.data!r}")
                elif msg.type == MessageType.RESULT:
                    print(f"    Result: {msg.repr}")
                elif msg.type == MessageType.ERROR:
                    print(f"    Error: {msg.traceback}")
                    
        except asyncio.TimeoutError:
            print(f"[{time.time()-start_time:.3f}s] TIMEOUT during execution")
            
            # Log timeout
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "tags": ["testing", "investigation", "observation"],
                "summary": "Execution hangs after sending message",
                "details": f"Code execution times out. Received {len(messages_received)} messages before timeout",
                "hypothesis": "Worker not processing execute messages",
                "falsification_steps": "Check message routing, verify execute handler",
                "outcome": "Execution loop may be blocked",
                "notes": f"Messages received: {[m.type for m in messages_received]}"
            }
            
            # Append to investigation log
            log_file = Path(__file__).parent.parent.parent / "troubleshooting" / "investigation_log.json"
            if log_file.exists():
                with open(log_file) as f:
                    logs = json.load(f)
                logs.append(log_entry)
                with open(log_file, 'w') as f:
                    json.dump(logs, f, indent=2)
            
            return False
        
        elapsed = time.time() - start_time
        print(f"[{elapsed:.3f}s] Execution completed successfully!")
        print(f"  Messages received: {len(messages_received)}")
        
        # Log success
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tags": ["testing", "validation"],
            "summary": "Simple execution works",
            "details": f"Code executed successfully. Received {len(messages_received)} messages",
            "hypothesis": None,
            "falsification_steps": None,
            "outcome": "Basic execution functioning",
            "notes": f"Message types: {[m.type for m in messages_received]}"
        }
        
        # Append to investigation log
        log_file = Path(__file__).parent.parent.parent / "troubleshooting" / "investigation_log.json"
        if log_file.exists():
            with open(log_file) as f:
                logs = json.load(f)
            logs.append(log_entry)
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[{elapsed:.3f}s] ERROR: {type(e).__name__}: {e}")
        
        import traceback
        traceback.print_exc()
        
        # Log error
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tags": ["testing", "error"],
            "summary": f"Execution error: {type(e).__name__}",
            "details": str(e),
            "hypothesis": None,
            "falsification_steps": None,
            "outcome": "Unexpected error",
            "notes": None
        }
        
        # Append to investigation log
        log_file = Path(__file__).parent.parent.parent / "troubleshooting" / "investigation_log.json"
        if log_file.exists():
            with open(log_file) as f:
                logs = json.load(f)
            logs.append(log_entry)
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        
        return False
        
    finally:
        try:
            await session.terminate()
        except:
            pass


if __name__ == "__main__":
    success = asyncio.run(test_simple_execution())
    sys.exit(0 if success else 1)