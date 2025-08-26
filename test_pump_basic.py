#!/usr/bin/env python3
"""
Basic test to debug the output pump mechanism.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, ResultMessage, OutputMessage


async def test_basic_output():
    """Test basic output with debugging."""
    print("Testing basic output with new pump mechanism...")
    
    session = Session()
    await session.start()
    
    try:
        # Simple test
        code = 'print("Hello World")'
        msg = ExecuteMessage(
            id="test",
            timestamp=time.time(),
            code=code
        )
        
        print(f"Executing: {code}")
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
            if response.type == 'error':
                print(f"ERROR: {getattr(response, 'exception_message', 'Unknown error')}")
                print(f"Traceback: {getattr(response, 'traceback', 'No traceback')}")
            else:
                print(f"Received: {response.type} - {getattr(response, 'data', None)}")
        
        # Check what we got
        output_msgs = [m for m in messages if isinstance(m, OutputMessage)]
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        
        print(f"\nSummary:")
        print(f"  Output messages: {len(output_msgs)}")
        print(f"  Output text: {repr(''.join(m.data for m in output_msgs))}")
        print(f"  Result: {result_msg.value if result_msg else None}")
        
    finally:
        await session.shutdown()


if __name__ == "__main__":
    # Enable debug logging
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    asyncio.run(test_basic_output())