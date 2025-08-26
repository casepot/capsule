#!/usr/bin/env python3
"""
Simple test to verify the event-driven output handling works.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType


async def test_simple():
    """Test simple output."""
    print("Testing simple output...")
    
    session = Session()
    await session.start()
    
    try:
        code = 'print("Hello, World!")'
        msg = ExecuteMessage(
            id="simple",
            timestamp=0,
            code=code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
            print(f"  Received: {response.type}")
            if response.type == MessageType.OUTPUT:
                print(f"    Data: {repr(response.data)}")
        
        # Check we got both output and result
        output_msgs = [m for m in messages if m.type == MessageType.OUTPUT]
        result_msgs = [m for m in messages if m.type == MessageType.RESULT]
        
        print(f"\nGot {len(output_msgs)} output messages")
        print(f"Got {len(result_msgs)} result messages")
        
        if output_msgs:
            print(f"Output: {repr(output_msgs[0].data)}")
        
        assert len(output_msgs) > 0, "Should have output"
        assert len(result_msgs) > 0, "Should have result"
        assert "Hello, World!" in output_msgs[0].data
        
        print("✅ Test passed!")
        
    finally:
        await session.shutdown()


if __name__ == "__main__":
    asyncio.run(test_simple())