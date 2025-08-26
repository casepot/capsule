#!/usr/bin/env python3
"""Detailed test of warmup flow to find where it blocks."""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Enable debug logging
import structlog
import logging
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    processors=[structlog.dev.ConsoleRenderer()],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

from src.session.manager import Session, SessionState
from src.protocol.messages import ExecuteMessage

async def test_warmup_detailed():
    """Test warmup with detailed tracing."""
    
    print("="*60)
    print("DETAILED WARMUP FLOW TEST")
    print("="*60)
    
    # Override _warmup to add more logging
    original_warmup = Session._warmup
    
    async def traced_warmup(self):
        """Traced version of _warmup."""
        print(f"\n[TRACE] _warmup called, state={self._state}")
        
        if not self._warmup_code:
            print("[TRACE] No warmup code, returning")
            return
        
        print(f"[TRACE] Creating ExecuteMessage for warmup")
        message = ExecuteMessage(
            type="execute",  # Explicit type
            id="warmup-test",
            timestamp=time.time(),
            code=self._warmup_code,
            capture_source=False,
        )
        
        print(f"[TRACE] ExecuteMessage created: type={message.type}, id={message.id}")
        print(f"[TRACE] Calling self.execute(), state={self._state}")
        
        try:
            msg_count = 0
            # Add timeout to the execute iteration
            async with asyncio.timeout(5.0):
                async for msg in self.execute(message):
                    msg_count += 1
                    print(f"[TRACE] Warmup received message {msg_count}: {msg.type}")
            
            print(f"[TRACE] Warmup complete, received {msg_count} messages")
        except asyncio.TimeoutError:
            print(f"[TRACE] ERROR: Warmup execute timed out!")
            raise
        except Exception as e:
            print(f"[TRACE] ERROR in warmup: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    # Monkey patch
    Session._warmup = traced_warmup
    
    try:
        print("\nCreating session with warmup code...")
        session = Session(warmup_code="print('Warmup!'); x = 42")
        
        print(f"Session created, state={session.state}")
        print("\nCalling session.start()...")
        
        await asyncio.wait_for(session.start(), timeout=10.0)
        
        print(f"\n✓ Session started! State={session.state}")
        
        # Test if warmup worked
        test_msg = ExecuteMessage(
            type="execute",
            id="test",
            timestamp=time.time(),
            code="print(f'x={x}')",
            capture_source=False
        )
        
        print("\nTesting if warmup variable exists...")
        async for msg in session.execute(test_msg):
            if msg.type == "output":
                print(f"Output: {msg.data}")
        
        await session.terminate()
        
    except asyncio.TimeoutError:
        print(f"\n✗ Session start timed out! State={session.state if 'session' in locals() else 'unknown'}")
        if 'session' in locals():
            await session.terminate()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        if 'session' in locals():
            await session.terminate()
    finally:
        # Restore original
        Session._warmup = original_warmup


async def test_manual_warmup_simulation():
    """Simulate what warmup should do manually."""
    
    print("\n" + "="*60)
    print("MANUAL WARMUP SIMULATION")
    print("="*60)
    
    print("\n1. Starting session WITHOUT warmup...")
    session = Session()
    await session.start()
    print(f"   Session state: {session.state}")
    
    print("\n2. Manually setting state to WARMING...")
    session._state = SessionState.WARMING
    print(f"   Session state: {session.state}")
    
    print("\n3. Trying to execute while in WARMING state...")
    warmup_msg = ExecuteMessage(
        type="execute",
        id="manual-warmup",
        timestamp=time.time(),
        code="manual_warmup = True",
        capture_source=False
    )
    
    try:
        messages = []
        async with asyncio.timeout(3.0):
            async for msg in session.execute(warmup_msg):
                messages.append(msg)
                print(f"   Received: {msg.type}")
        
        print(f"   ✓ Execute worked in WARMING state! {len(messages)} messages")
        
    except asyncio.TimeoutError:
        print("   ✗ Execute timed out in WARMING state!")
    except Exception as e:
        print(f"   ✗ Execute failed: {e}")
    
    print("\n4. Setting state back to READY...")
    session._state = SessionState.READY
    
    print("\n5. Testing normal execution...")
    test_msg = ExecuteMessage(
        type="execute",
        id="test",
        timestamp=time.time(),
        code="print('Normal')",
        capture_source=False
    )
    
    messages = []
    async for msg in session.execute(test_msg):
        messages.append(msg)
        print(f"   Received: {msg.type}")
    
    print(f"   Received {len(messages)} messages")
    
    await session.terminate()


async def main():
    """Run warmup flow tests."""
    await test_warmup_detailed()
    await test_manual_warmup_simulation()
    
    print("\n" + "="*60)
    print("WARMUP FLOW ANALYSIS COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())