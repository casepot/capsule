#!/usr/bin/env python3
"""Capture full worker error traceback."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def test_worker_error():
    """Capture worker startup errors."""
    print("=" * 50)
    print("TEST: Worker Error Capture")
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
    
    # Wait for process to complete or timeout
    try:
        returncode = await asyncio.wait_for(process.wait(), timeout=3.0)
        print(f"Process exited with code: {returncode}")
    except asyncio.TimeoutError:
        print("Process still running after 3 seconds")
        process.terminate()
        await process.wait()
    
    # Read all stderr
    stderr_data = await process.stderr.read()
    if stderr_data:
        print("\n" + "=" * 30 + " STDERR " + "=" * 30)
        print(stderr_data.decode('utf-8', errors='replace'))
        print("=" * 68 + "\n")
    
    # Read all stdout
    stdout_data = await process.stdout.read()
    if stdout_data:
        print("\n" + "=" * 30 + " STDOUT " + "=" * 30)
        print(f"Raw bytes (first 200): {stdout_data[:200]}")
        print("=" * 68 + "\n")


if __name__ == "__main__":
    asyncio.run(test_worker_error())