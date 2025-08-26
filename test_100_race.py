#!/usr/bin/env python3
"""Test 100 iterations of simple print to check race conditions."""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType


async def test_100_prints():
    """Test 100 simple prints."""
    print("Testing 100 simple prints...")
    
    session = Session()
    await session.start()
    
    failures = 0
    missing_outputs = 0
    order_violations = 0
    
    try:
        for i in range(100):
            if i % 10 == 0:
                print(f"  Progress: {i}/100")
                
            code = f'print("x{i}")'
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
            
            if len(output_msgs) == 0:
                missing_outputs += 1
                failures += 1
                print(f"    Test {i}: MISSING OUTPUT!")
            elif len(result_msgs) == 0:
                failures += 1
                print(f"    Test {i}: MISSING RESULT!")
            else:
                # Check ordering
                last_output_idx = messages.index(output_msgs[-1])
                first_result_idx = messages.index(result_msgs[0])
                if last_output_idx >= first_result_idx:
                    order_violations += 1
                    failures += 1
                    print(f"    Test {i}: ORDER VIOLATION!")
    
    finally:
        await session.shutdown()
    
    print(f"\nResults: {100 - failures}/100 passed")
    print(f"  Missing outputs: {missing_outputs}")
    print(f"  Order violations: {order_violations}")
    
    if failures == 0:
        print("✅ All tests passed - no race conditions!")
        return 0
    else:
        print(f"❌ {failures} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(test_100_prints()))