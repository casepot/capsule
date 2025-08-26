#!/usr/bin/env python3
"""
Test the queue mechanism directly.
"""

import asyncio
import queue
import time


async def test_queue():
    """Test queue operations."""
    print("Testing queue mechanism...")
    
    # Create a queue
    q = queue.Queue(maxsize=1024)
    
    # Put item in queue from sync context
    q.put(("Test message", "stdout"), timeout=1.0)
    print(f"Put item in queue, size: {q.qsize()}")
    
    # Try to get from async context
    loop = asyncio.get_running_loop()
    
    try:
        item = await asyncio.wait_for(
            loop.run_in_executor(None, q.get, True, 0.1),
            timeout=0.5
        )
        print(f"Got item from queue: {item}")
    except asyncio.TimeoutError:
        print("Timeout getting from queue")
    
    print(f"Queue size after get: {q.qsize()}")


if __name__ == "__main__":
    asyncio.run(test_queue())