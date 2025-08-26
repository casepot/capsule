#!/usr/bin/env python3
"""
Simple transport layer investigation focusing on the core issue.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def test_subprocess_rapid_creation():
    """Test rapid subprocess creation to see if it causes issues."""
    print("\n=== Subprocess Rapid Creation Test ===")
    
    import subprocess
    
    failures = 0
    for i in range(20):
        try:
            # Start a Python subprocess
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "print('test')",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait for it to complete
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=2.0
            )
            
            if proc.returncode != 0:
                failures += 1
                print(f"  Process {i}: EXIT CODE {proc.returncode}")
            
        except asyncio.TimeoutError:
            failures += 1
            print(f"  Process {i}: TIMEOUT")
            if proc:
                proc.kill()
                await proc.wait()
        except Exception as e:
            failures += 1
            print(f"  Process {i}: ERROR - {e}")
    
    print(f"  Completed: {20 - failures}/20 subprocesses")
    
    if failures == 0:
        print("  ✅ All subprocesses created successfully")
    else:
        print(f"  ❌ {failures} subprocess failures")
    
    return failures == 0


async def test_session_message_pattern():
    """Test the actual message pattern from a session."""
    print("\n=== Session Message Pattern Test ===")
    
    from src.session.manager import Session
    from src.protocol.messages import ExecuteMessage
    
    # Create one session and use it multiple times
    session = Session()
    
    try:
        await asyncio.wait_for(session.start(), timeout=10.0)
        print("  Session started successfully")
        
        failures = 0
        
        # Run multiple executions on same session
        for i in range(50):
            try:
                msg = ExecuteMessage(
                    id=f"test-{i}",
                    timestamp=time.time(),
                    code=f"print('test_{i}')"
                )
                
                messages = []
                async for response in session.execute(msg, timeout=2.0):
                    messages.append(response)
                
                # Check we got output
                has_output = any(m.type == "output" for m in messages)
                has_result = any(m.type == "result" for m in messages)
                
                if not has_output or not has_result:
                    failures += 1
                    print(f"  Execution {i}: Missing {'output' if not has_output else 'result'}")
                    
            except asyncio.TimeoutError:
                failures += 1
                print(f"  Execution {i}: TIMEOUT")
            except Exception as e:
                failures += 1
                print(f"  Execution {i}: ERROR - {e}")
        
        print(f"  Completed {50 - failures}/50 executions")
        
        if failures == 0:
            print("  ✅ All executions successful on single session")
            return True
        else:
            print(f"  ❌ {failures} execution failures")
            return False
            
    except asyncio.TimeoutError:
        print("  ❌ Session start timeout")
        return False
    except Exception as e:
        print(f"  ❌ Session error: {e}")
        return False
    finally:
        try:
            await session.shutdown()
        except:
            pass


async def test_message_sizes():
    """Test different message sizes through a session."""
    print("\n=== Message Size Test ===")
    
    from src.session.manager import Session
    from src.protocol.messages import ExecuteMessage
    
    session = Session()
    
    try:
        await asyncio.wait_for(session.start(), timeout=10.0)
        
        # Test various output sizes
        test_cases = [
            ("tiny", 1),
            ("small", 10),
            ("medium", 100),
            ("large", 1000),
            ("huge", 10000),
            ("massive", 100000),
        ]
        
        failures = 0
        
        for name, size in test_cases:
            try:
                # Generate code that produces specific output size
                code = f"print('x' * {size})"
                
                msg = ExecuteMessage(
                    id=f"size-{name}",
                    timestamp=time.time(),
                    code=code
                )
                
                output_size = 0
                async for response in session.execute(msg, timeout=5.0):
                    if response.type == "output":
                        output_size += len(response.data)
                
                # Check we got approximately the right size (plus newline)
                expected = size + 1  # +1 for newline
                if abs(output_size - expected) > 10:
                    print(f"  {name:8s} ({size:6d}): Size mismatch - got {output_size}, expected ~{expected}")
                    failures += 1
                else:
                    print(f"  {name:8s} ({size:6d}): OK")
                    
            except asyncio.TimeoutError:
                print(f"  {name:8s} ({size:6d}): TIMEOUT")
                failures += 1
            except Exception as e:
                print(f"  {name:8s} ({size:6d}): ERROR - {e}")
                failures += 1
        
        if failures == 0:
            print("  ✅ All message sizes handled correctly")
            return True
        else:
            print(f"  ❌ {failures} size tests failed")
            return False
            
    finally:
        try:
            await session.shutdown()
        except:
            pass


async def test_concurrent_executions():
    """Test concurrent executions on same session (should be serialized)."""
    print("\n=== Concurrent Execution Test ===")
    
    from src.session.manager import Session
    from src.protocol.messages import ExecuteMessage
    
    session = Session()
    
    try:
        await asyncio.wait_for(session.start(), timeout=10.0)
        
        async def run_execution(exec_id: str):
            """Run a single execution."""
            msg = ExecuteMessage(
                id=exec_id,
                timestamp=time.time(),
                code=f"import time; time.sleep(0.01); print('{exec_id}')"
            )
            
            outputs = []
            async for response in session.execute(msg, timeout=5.0):
                if response.type == "output":
                    outputs.append(response.data)
            
            return exec_id, outputs
        
        # Start multiple executions concurrently
        # They should be serialized by the session
        tasks = [
            run_execution(f"concurrent-{i}")
            for i in range(5)
        ]
        
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=30.0
        )
        
        # Check results
        failures = 0
        for result in results:
            if isinstance(result, Exception):
                print(f"  Execution failed: {result}")
                failures += 1
            else:
                exec_id, outputs = result
                output_text = "".join(outputs)
                if exec_id not in output_text:
                    print(f"  {exec_id}: Output mismatch")
                    failures += 1
        
        if failures == 0:
            print("  ✅ All concurrent executions handled correctly")
            return True
        else:
            print(f"  ❌ {failures} concurrent execution failures")
            return False
            
    finally:
        try:
            await session.shutdown()
        except:
            pass


async def main():
    """Run transport investigation tests."""
    print("=" * 60)
    print("Transport Layer Investigation (Simplified)")
    print("=" * 60)
    
    tests = [
        test_subprocess_rapid_creation,
        test_session_message_pattern,
        test_message_sizes,
        test_concurrent_executions,
    ]
    
    results = []
    for test in tests:
        try:
            result = await asyncio.wait_for(test(), timeout=60.0)
            results.append((test.__name__, result))
        except asyncio.TimeoutError:
            print(f"\n{test.__name__}: TIMEOUT")
            results.append((test.__name__, False))
        except Exception as e:
            print(f"\n{test.__name__}: ERROR - {e}")
            results.append((test.__name__, False))
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{name:35s}: {status}")


if __name__ == "__main__":
    asyncio.run(main())
    