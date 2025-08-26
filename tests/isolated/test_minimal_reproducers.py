#!/usr/bin/env python3
"""Minimal reproducible test cases for each remaining issue."""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Suppress logs for clarity
import structlog
import logging
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR),
)


def test_issue_1_warmup_hang():
    """Issue 1: Session with warmup hangs indefinitely."""
    print("\n" + "="*60)
    print("ISSUE 1: Warmup Hang")
    print("="*60)
    
    from src.session.manager import Session
    
    async def run():
        print("Creating session WITH warmup code...")
        session = Session(warmup_code="warmup_var = 123")
        
        print("Starting session (should complete in <1s)...")
        try:
            await asyncio.wait_for(session.start(), timeout=3.0)
            print("✅ SUCCESS: Session started with warmup!")
            await session.terminate()
            return True
        except asyncio.TimeoutError:
            print("❌ FAIL: Session start timed out after 3s")
            await session.terminate()
            return False
        except Exception as e:
            print(f"❌ ERROR: {e}")
            return False
    
    return asyncio.run(run())


def test_issue_2_pool_parameters():
    """Issue 2: SessionPool doesn't accept expected parameters."""
    print("\n" + "="*60)
    print("ISSUE 2: Pool Parameter Mismatch")
    print("="*60)
    
    from src.session.pool import SessionPool
    
    print("Trying to create pool with min_size and max_size...")
    try:
        pool = SessionPool(min_size=2, max_size=5)
        print("✅ SUCCESS: Pool created with keyword arguments")
        return True
    except TypeError as e:
        print(f"❌ FAIL: {e}")
        
        print("\nWorkaround: Using PoolConfig...")
        try:
            from src.session.pool import PoolConfig
            config = PoolConfig()
            config.min_idle = 2
            config.max_sessions = 5
            pool = SessionPool(config)
            print("✅ Workaround successful with PoolConfig")
        except Exception as e2:
            print(f"❌ Even workaround failed: {e2}")
        
        return False


def test_issue_3_execute_in_warming():
    """Issue 3: Execute during WARMING state."""
    print("\n" + "="*60)
    print("ISSUE 3: Execute in WARMING State")
    print("="*60)
    
    from src.session.manager import Session, SessionState
    from src.protocol.messages import ExecuteMessage
    
    async def run():
        print("Creating session without warmup...")
        session = Session()
        await session.start()
        
        print(f"Current state: {session.state}")
        
        print("Manually setting state to WARMING...")
        session._state = SessionState.WARMING
        print(f"Current state: {session.state}")
        
        print("Trying to execute code while in WARMING state...")
        msg = ExecuteMessage(
            type="execute",
            id="test",
            timestamp=time.time(),
            code="test = 42",
            capture_source=False
        )
        
        try:
            messages = []
            async with asyncio.timeout(2.0):
                async for response in session.execute(msg):
                    messages.append(response)
                    
            print(f"✅ SUCCESS: Execute worked in WARMING state, got {len(messages)} messages")
            await session.terminate()
            return True
            
        except asyncio.TimeoutError:
            print("❌ FAIL: Execute timed out in WARMING state")
            await session.terminate()
            return False
        except RuntimeError as e:
            print(f"❌ FAIL: {e}")
            await session.terminate()
            return False
    
    return asyncio.run(run())


def test_working_case():
    """Demonstrate what DOES work."""
    print("\n" + "="*60)
    print("WORKING: Basic Session Without Warmup")
    print("="*60)
    
    from src.session.manager import Session
    from src.protocol.messages import ExecuteMessage
    
    async def run():
        print("Creating session WITHOUT warmup...")
        session = Session()
        
        print("Starting session...")
        await session.start()
        print(f"✓ Started, state: {session.state}")
        
        print("Executing code...")
        msg = ExecuteMessage(
            type="execute",
            id="test",
            timestamp=time.time(),
            code="result = 2 + 2\nprint(f'Result: {result}')",
            capture_source=False
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
            print(f"  Received: {response.type}")
        
        print(f"✓ Got {len(messages)} messages")
        
        print("Terminating...")
        await session.terminate()
        print("✓ Complete!")
        
        return len(messages) > 0
    
    return asyncio.run(run())


def main():
    """Run all minimal reproducers."""
    print("="*60)
    print("MINIMAL REPRODUCIBLE TEST CASES")
    print("="*60)
    print("\nThese tests demonstrate each remaining issue in isolation.")
    
    results = {}
    
    # Test each issue
    results["Issue 1: Warmup Hang"] = test_issue_1_warmup_hang()
    results["Issue 2: Pool Parameters"] = test_issue_2_pool_parameters()
    results["Issue 3: WARMING State"] = test_issue_3_execute_in_warming()
    results["Working Case"] = test_working_case()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("\nConclusion:")
    if results["Working Case"]:
        print("✓ Core functionality works when warmup is not used")
    
    failures = [name for name, passed in results.items() if not passed and name != "Working Case"]
    if failures:
        print(f"✗ {len(failures)} critical issues remain:")
        for issue in failures:
            print(f"  - {issue}")
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)