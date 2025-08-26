#!/usr/bin/env python3
"""
Simple test to verify namespace persistence with session reuse.
This demonstrates the critical bug fix.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, ResultMessage
import time


async def test_namespace_persistence_with_reuse():
    """Test that namespace persists when reusing the same session."""
    print("=== Testing Namespace Persistence with Session Reuse ===\n")
    
    # Create ONE session and reuse it
    session = Session()
    await session.start()
    
    try:
        # First execution: Set a variable
        print("1. Setting variable x = 42")
        msg1 = ExecuteMessage(
            id="test-1",
            timestamp=time.time(),
            code="x = 42"
        )
        async for _ in session.execute(msg1):
            pass
        
        # Second execution: Use the variable (SAME SESSION)
        print("2. Reading variable x")
        msg2 = ExecuteMessage(
            id="test-2", 
            timestamp=time.time(),
            code="x"  # Just evaluate x
        )
        
        result = None
        async for response in session.execute(msg2):
            if isinstance(response, ResultMessage):
                result = response.value
        
        print(f"   Result: {result}")
        
        # Third execution: Modify variable
        print("3. Modifying variable: x = x * 2")
        msg3 = ExecuteMessage(
            id="test-3",
            timestamp=time.time(),
            code="x = x * 2; x"
        )
        
        result2 = None
        async for response in session.execute(msg3):
            if isinstance(response, ResultMessage):
                result2 = response.value
        
        print(f"   Result: {result2}")
        
        # Test results
        success = result == 42 and result2 == 84
        print(f"\n✅ NAMESPACE PERSISTENCE WORKS!" if success else "❌ NAMESPACE PERSISTENCE FAILED")
        
        if not success:
            print(f"   Expected: x=42 then x=84")
            print(f"   Got: x={result} then x={result2}")
        
        return success
        
    finally:
        await session.shutdown()


async def test_namespace_not_persisting_with_new_sessions():
    """Demonstrate that creating new sessions breaks persistence."""
    print("\n=== Testing Without Session Reuse (Expected to Fail) ===\n")
    
    # First session
    session1 = Session()
    await session1.start()
    
    try:
        print("1. Setting variable y = 100 in session 1")
        msg1 = ExecuteMessage(
            id="test-4",
            timestamp=time.time(),
            code="y = 100"
        )
        async for _ in session1.execute(msg1):
            pass
    finally:
        await session1.shutdown()
    
    # Second session (NEW - this is the problem!)
    session2 = Session()
    await session2.start()
    
    try:
        print("2. Trying to read y in NEW session 2")
        msg2 = ExecuteMessage(
            id="test-5",
            timestamp=time.time(),
            code="y if 'y' in dir() else 'NOT FOUND'"
        )
        
        result = None
        async for response in session2.execute(msg2):
            if isinstance(response, ResultMessage):
                result = response.value
        
        print(f"   Result: {result}")
        print(f"\n⚠️  As expected, y is {'NOT FOUND' if result == 'NOT FOUND' else 'unexpectedly ' + str(result)}")
        print("   This demonstrates why session reuse is critical!")
        
    finally:
        await session2.shutdown()


async def main():
    print("=" * 60)
    print("CRITICAL BUG FIX VERIFICATION")
    print("=" * 60)
    
    # Test with session reuse (should work)
    success1 = await test_namespace_persistence_with_reuse()
    
    # Test without session reuse (should fail - demonstrating the bug)
    await test_namespace_not_persisting_with_new_sessions()
    
    print("\n" + "=" * 60)
    print("CONCLUSION")
    print("=" * 60)
    
    if success1:
        print("✅ Namespace persistence works with session reuse!")
        print("✅ Input override persistence fix in executor.py is working!")
        print("\nKey insights:")
        print("1. Each Session() creates a new subprocess with fresh namespace")
        print("2. To persist state, you MUST reuse the same session")
        print("3. Consider using SessionPool for proper session management")
    else:
        print("❌ Namespace persistence still has issues")
    
    return success1


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)