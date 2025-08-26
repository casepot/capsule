#!/usr/bin/env python3
"""Test that main.py runs without hanging."""

import asyncio
import sys
import time
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def test_main_with_timeout():
    """Test main.py with timeout."""
    print("=" * 50)
    print("TEST: main.py execution")
    print("=" * 50)
    
    start_time = time.time()
    
    try:
        # Import main and run it with timeout
        from main import main
        print(f"[{time.time()-start_time:.3f}s] Running main()...")
        
        await asyncio.wait_for(main(), timeout=15.0)
        
        elapsed = time.time() - start_time
        print(f"[{elapsed:.3f}s] main() completed successfully!")
        
        # Log success
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tags": ["testing", "validation", "root_cause"],
            "summary": "main.py runs successfully",
            "details": f"main.py completed all demos in {elapsed:.3f}s without hanging",
            "hypothesis": None,
            "falsification_steps": None,
            "outcome": "Issue resolved - all fixes working",
            "notes": "Worker communication and async issues fixed"
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
        print(f"\n[{elapsed:.3f}s] TIMEOUT: main() did not complete within 15 seconds")
        
        # Log timeout
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tags": ["testing", "investigation"],
            "summary": "main.py still hanging",
            "details": f"main() timed out after {elapsed:.3f}s",
            "hypothesis": "Additional async issues remain",
            "falsification_steps": "Add more logging, check for deadlocks in pool",
            "outcome": "Further investigation needed",
            "notes": "Worker starts but something else blocks"
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
        print(f"\n[{elapsed:.3f}s] ERROR: {type(e).__name__}: {e}")
        
        # Log error
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tags": ["testing", "investigation", "error"],
            "summary": f"main.py error: {type(e).__name__}",
            "details": str(e),
            "hypothesis": None,
            "falsification_steps": None,
            "outcome": "Unexpected error occurred",
            "notes": "Check stack trace"
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


if __name__ == "__main__":
    success = asyncio.run(test_main_with_timeout())
    sys.exit(0 if success else 1)