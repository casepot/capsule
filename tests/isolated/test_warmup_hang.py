#!/usr/bin/env python3
"""Focused test to isolate warmup hanging issue."""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage


async def test_warmup_stages():
    """Test warmup at different stages to find where it hangs."""
    
    print("="*60)
    print("TEST: Warmup Hang Isolation")
    print("="*60)
    
    # Test 1: Session without warmup (baseline)
    print("\n1. Testing session WITHOUT warmup...")
    try:
        session1 = Session()
        await asyncio.wait_for(session1.start(), timeout=5.0)
        print("   ✓ Started successfully")
        await session1.terminate()
    except asyncio.TimeoutError:
        print("   ✗ Timed out!")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Test 2: Session with minimal warmup
    print("\n2. Testing session with MINIMAL warmup (x=1)...")
    try:
        session2 = Session(warmup_code="x = 1")
        print("   Created session, calling start()...")
        
        # Start with longer timeout to see what happens
        await asyncio.wait_for(session2.start(), timeout=5.0)
        print(f"   ✓ Started successfully, state: {session2.state}")
        await session2.terminate()
    except asyncio.TimeoutError:
        print(f"   ✗ Timed out! Session state: {session2.state}")
        # Force terminate
        await session2.terminate()
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Manual warmup execution
    print("\n3. Testing manual warmup execution...")
    try:
        session3 = Session()
        print("   Starting session without warmup...")
        await asyncio.wait_for(session3.start(), timeout=5.0)
        print(f"   Session started, state: {session3.state}")
        
        # Now manually execute warmup code
        print("   Executing warmup code manually...")
        warmup_msg = ExecuteMessage(
            type="execute",
            id="warmup",
            timestamp=time.time(),
            code="warmup_test = 42",
            capture_source=False
        )
        
        messages = []
        async for msg in asyncio.wait_for(session3.execute(warmup_msg), timeout=5.0):
            messages.append(msg)
            print(f"     Received: {msg.type}")
        
        print(f"   ✓ Manual warmup executed, {len(messages)} messages")
        await session3.terminate()
        
    except asyncio.TimeoutError:
        print(f"   ✗ Timed out! Session state: {session3.state}")
        await session3.terminate()
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 4: Check _warmup method directly
    print("\n4. Testing _warmup method in isolation...")
    try:
        session4 = Session(warmup_code="test_var = 123")
        
        # Manually setup like start() does
        print("   Creating subprocess...")
        session4._process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "src.subprocess.worker",
            session4.session_id,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        print("   Creating transport...")
        from src.session.pool import PipeTransport
        session4._transport = PipeTransport(session4._process, use_msgpack=True)
        await session4._transport.start()
        
        print("   Starting receive task...")
        session4._receive_task = asyncio.create_task(session4._receive_loop())
        
        print("   Setting state to WARMING...")
        session4._state = session4.state.__class__.WARMING
        
        print("   Waiting for ready event...")
        try:
            await asyncio.wait_for(session4._ready_event.wait(), timeout=3.0)
            print("   ✓ Got ready event")
        except asyncio.TimeoutError:
            print("   ✗ No ready event received")
        
        if session4._warmup_code:
            print("   Calling _warmup()...")
            try:
                await asyncio.wait_for(session4._warmup(), timeout=3.0)
                print("   ✓ Warmup completed")
            except asyncio.TimeoutError:
                print("   ✗ Warmup timed out!")
                # Check what's happening
                print(f"   Session state: {session4.state}")
            except Exception as e:
                print(f"   ✗ Warmup error: {e}")
                import traceback
                traceback.print_exc()
        
        await session4.terminate()
        
    except Exception as e:
        print(f"   ✗ Setup error: {e}")
        import traceback
        traceback.print_exc()


async def test_warmup_message_flow():
    """Test the message flow during warmup."""
    
    print("\n" + "="*60)
    print("TEST: Warmup Message Flow Analysis")
    print("="*60)
    
    # Enable debug logging for this test
    import structlog
    import logging
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        processors=[structlog.dev.ConsoleRenderer()],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    
    print("\n5. Testing warmup message flow with debug logging...")
    
    try:
        session = Session(warmup_code="print('Warmup running'); warmup_done = True")
        
        print("   Starting session with warmup (debug logging enabled)...")
        print("   [Watch for message flow below]")
        print("-" * 40)
        
        # Use a longer timeout to capture all debug output
        await asyncio.wait_for(session.start(), timeout=3.0)
        
        print("-" * 40)
        print(f"   ✓ Session started! State: {session.state}")
        
        # Test if warmup variable exists
        test_msg = ExecuteMessage(
            type="execute",
            id="test_warmup",
            timestamp=time.time(),
            code="print(f'Warmup done: {warmup_done}')",
            capture_source=False
        )
        
        async for msg in session.execute(test_msg):
            if msg.type == "output":
                print(f"   Output confirms warmup: {msg.data}")
        
        await session.terminate()
        
    except asyncio.TimeoutError:
        print("-" * 40)
        print(f"   ✗ Timed out during warmup! State: {session.state}")
        await session.terminate()
    except Exception as e:
        print("-" * 40)
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Run all warmup tests."""
    # First run without debug logs
    import structlog
    import logging
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    )
    
    await test_warmup_stages()
    await test_warmup_message_flow()
    
    print("\n" + "="*60)
    print("WARMUP HANG ANALYSIS COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())