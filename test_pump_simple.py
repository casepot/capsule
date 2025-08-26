#!/usr/bin/env python3
"""
Simple test of the pump mechanism
"""

import asyncio
import queue
import time
from src.subprocess.executor import ThreadedExecutor
from src.protocol.messages import StreamType


class FakeTransport:
    async def send_message(self, msg):
        print(f"[TRANSPORT] Sending: {msg.type} - {getattr(msg, 'data', None)[:50] if hasattr(msg, 'data') else 'N/A'}")


async def test():
    """Test the pump directly."""
    transport = FakeTransport()
    loop = asyncio.get_running_loop()
    
    executor = ThreadedExecutor(
        transport=transport,
        execution_id="test-123",
        namespace={},
        loop=loop
    )
    
    # Start the pump
    await executor.start_output_pump()
    print("[TEST] Pump started")
    
    # Put something in the queue directly
    print(f"[TEST] Queue size before: {executor._output_queue.qsize()}")
    executor._output_queue.put(("Hello from queue!\n", StreamType.STDOUT))
    print(f"[TEST] Queue size after: {executor._output_queue.qsize()}")
    
    # Give pump time to process
    await asyncio.sleep(1)
    
    # Shutdown
    executor.shutdown_pump()
    if executor._pump_task:
        await executor._pump_task
    
    print("[TEST] Done")


if __name__ == "__main__":
    asyncio.run(test())