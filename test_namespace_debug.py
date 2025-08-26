#!/usr/bin/env python3
"""
Debug test to understand namespace behavior.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, ResultMessage
import time


async def test_namespace_debug():
    """Debug namespace behavior."""
    print("=== Namespace Debug Test ===\n")
    
    session = Session()
    await session.start()
    
    try:
        # First, let's check what's in the initial namespace
        print("1. Checking initial namespace")
        msg1 = ExecuteMessage(
            id="debug-1",
            timestamp=time.time(),
            code="list(dir())[:10]"  # Show first 10 items
        )
        result = None
        async for response in session.execute(msg1):
            if isinstance(response, ResultMessage):
                result = response.value
        print(f"   Initial namespace items: {result}")
        
        # Set a variable
        print("\n2. Setting x = 42")
        msg2 = ExecuteMessage(
            id="debug-2",
            timestamp=time.time(),
            code="x = 42"
        )
        async for _ in session.execute(msg2):
            pass
        
        # Check if x is in namespace
        print("\n3. Checking if x is in namespace")
        msg3 = ExecuteMessage(
            id="debug-3",
            timestamp=time.time(),
            code="'x' in dir()"
        )
        result2 = None
        async for response in session.execute(msg3):
            if isinstance(response, ResultMessage):
                result2 = response.value
        print(f"   'x' in dir(): {result2}")
        
        # Try to get x value directly
        print("\n4. Getting x value")
        msg4 = ExecuteMessage(
            id="debug-4",
            timestamp=time.time(),
            code="x"
        )
        result3 = None
        async for response in session.execute(msg4):
            if isinstance(response, ResultMessage):
                result3 = response.value
        print(f"   x = {result3}")
        
        # Try a different approach - get locals
        print("\n5. Checking locals()")
        msg5 = ExecuteMessage(
            id="debug-5",
            timestamp=time.time(),
            code="'x' in locals()"
        )
        result4 = None
        async for response in session.execute(msg5):
            if isinstance(response, ResultMessage):
                result4 = response.value
        print(f"   'x' in locals(): {result4}")
        
        # Check globals
        print("\n6. Checking globals()")
        msg6 = ExecuteMessage(
            id="debug-6",
            timestamp=time.time(),
            code="'x' in globals()"
        )
        result5 = None
        async for response in session.execute(msg6):
            if isinstance(response, ResultMessage):
                result5 = response.value
        print(f"   'x' in globals(): {result5}")
        
        # Try setting and getting in one execution
        print("\n7. Set and get in one execution")
        msg7 = ExecuteMessage(
            id="debug-7",
            timestamp=time.time(),
            code="y = 100; y"
        )
        result6 = None
        async for response in session.execute(msg7):
            if isinstance(response, ResultMessage):
                result6 = response.value
        print(f"   y = {result6}")
        
        # Check if y persists
        print("\n8. Check if y persists")
        msg8 = ExecuteMessage(
            id="debug-8",
            timestamp=time.time(),
            code="y"
        )
        result7 = None
        async for response in session.execute(msg8):
            if isinstance(response, ResultMessage):
                result7 = response.value
        print(f"   y = {result7}")
        
        print("\n=== Analysis ===")
        print(f"x in dir(): {result2}")
        print(f"x value: {result3}")
        print(f"x in locals(): {result4}")
        print(f"x in globals(): {result5}")
        print(f"y (set and get): {result6}")
        print(f"y (persisted): {result7}")
        
        if result3 == 42 and result7 == 100:
            print("\n✅ Namespace persistence WORKS!")
        else:
            print("\n❌ Namespace persistence BROKEN")
        
    finally:
        await session.shutdown()


if __name__ == "__main__":
    asyncio.run(test_namespace_debug())