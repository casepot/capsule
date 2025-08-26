#!/usr/bin/env python3
"""Test that worker subprocess can start and send ready message."""

import asyncio
import sys
import time
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.session.manager import Session, SessionState


async def test_worker_startup():
    """Test worker can start and send ready message."""
    print("=" * 50)
    print("TEST: Worker Startup")
    print("=" * 50)
    
    start_time = time.time()
    session = Session()
    
    try:
        print(f"[{time.time()-start_time:.3f}s] Starting session...")
        
        # Start with timeout
        await asyncio.wait_for(session.start(), timeout=5.0)
        
        elapsed = time.time() - start_time
        print(f"[{elapsed:.3f}s] Session started successfully!")
        print(f"  Session ID: {session.session_id}")
        print(f"  State: {session.state}")
        print(f"  Is alive: {session.is_alive}")
        
        # Log success
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tags": ["testing", "validation", "breakthrough"],
            "summary": "Worker startup successful",
            "details": f"Worker started in {elapsed:.3f}s and reached READY state",
            "hypothesis": None,
            "falsification_steps": None,
            "outcome": "Worker communication fixed",
            "notes": "stdin/stdout connection working"
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
        
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"[{elapsed:.3f}s] TIMEOUT: Session failed to start within 5 seconds")
        print(f"  State: {session.state}")
        
        # Log failure
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tags": ["testing", "investigation"],
            "summary": "Worker startup timeout",
            "details": "Worker failed to send ready message within 5 seconds",
            "hypothesis": "Transport still not connected properly",
            "falsification_steps": "Check worker logs, verify pipe connection",
            "outcome": "Need further investigation",
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
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[{elapsed:.3f}s] ERROR: {type(e).__name__}: {e}")
        
        # Log error
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tags": ["testing", "investigation", "error"],
            "summary": f"Worker startup error: {type(e).__name__}",
            "details": str(e),
            "hypothesis": None,
            "falsification_steps": None,
            "outcome": "Unexpected error occurred",
            "notes": "Check stack trace for details"
        }
        
        # Append to investigation log
        log_file = Path(__file__).parent.parent.parent / "troubleshooting" / "investigation_log.json"
        if log_file.exists():
            with open(log_file) as f:
                logs = json.load(f)
            logs.append(log_entry)
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        try:
            await session.terminate()
        except:
            pass


if __name__ == "__main__":
    success = asyncio.run(test_worker_startup())
    sys.exit(0 if success else 1)