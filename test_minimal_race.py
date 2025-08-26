#!/usr/bin/env python3
"""
Minimal test to verify the race condition fix.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType


async def test_10_prints():
    """Test just 10 simple prints to see if ordering is preserved."""
    print("Testing 10 simple prints...")
    
    session = Session()
    await session.start()
    
    failures = 0
    
    try:
        for i in range(10):
            code = f'print("test_{i}")'
            msg = ExecuteMessage(
                id=f"test-{i}",
                timestamp=time.time(),
                code=code
            )
            
            messages = []
            async for response in session.execute(msg):
                messages.append(response)
            
            # Check we got both output and result
            output_msgs = [m for m in messages if m.type == MessageType.OUTPUT]
            result_msgs = [m for m in messages if m.type == MessageType.RESULT]
            
            print(f"  Test {i}: {len(output_msgs)} outputs, {len(result_msgs)} results", end="")
            
            if len(output_msgs) == 0:
                print(" - MISSING OUTPUT!")
                failures += 1
            elif len(result_msgs) == 0:
                print(" - MISSING RESULT!")
                failures += 1
            else:
                # Check ordering
                last_output_idx = messages.index(output_msgs[-1])
                first_result_idx = messages.index(result_msgs[0])
                if last_output_idx >= first_result_idx:
                    print(" - ORDER VIOLATION!")
                    failures += 1
                else:
                    print(" - OK")
    
    finally:
        await session.shutdown()
    
    print(f"\nResults: {10 - failures}/10 passed")
    
    if failures == 0:
        print("✅ All tests passed!")
    else:
        print(f"❌ {failures} tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_10_prints())