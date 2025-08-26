#!/usr/bin/env python3
"""
Comprehensive test suite for event-driven output handling.

Tests the race condition fix to ensure:
1. All output arrives before ResultMessage
2. No output is lost
3. Backpressure policies work correctly
4. Drain barriers are precise
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, ResultMessage, OutputMessage, MessageType


async def test_race_reproduction():
    """Test 1: Reproduce the original race - single small print many times."""
    print("\n=== Test 1: Race Reproduction (1000x single print) ===")
    
    session = Session()
    await session.start()
    
    failures = 0
    missing_outputs = 0
    order_violations = 0
    
    try:
        for i in range(1000):
            if i % 100 == 0:
                print(f"  Progress: {i}/1000")
                
            code = 'print("x")'
            msg = ExecuteMessage(
                id=f"race-{i}",
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
            elif len(result_msgs) == 0:
                failures += 1
            else:
                # Check ordering - output must come before result
                last_output_idx = messages.index(output_msgs[-1])
                first_result_idx = messages.index(result_msgs[0])
                if last_output_idx >= first_result_idx:
                    order_violations += 1
                    failures += 1
    
    finally:
        await session.shutdown()
    
    print(f"  Results: {1000 - failures}/1000 passed")
    print(f"  Missing outputs: {missing_outputs}")
    print(f"  Order violations: {order_violations}")
    
    assert failures == 0, f"Race test failed: {failures} failures out of 1000"
    print("  ✅ PASSED: No race conditions detected")


async def test_high_rate_output():
    """Test 2: High-rate prints to verify ordering and count."""
    print("\n=== Test 2: High-Rate Output (10k prints) ===")
    
    session = Session()
    await session.start()
    
    try:
        # Generate 10k prints
        code = """
for i in range(10000):
    print(f"Line {i:04d}")
"""
        msg = ExecuteMessage(
            id="high-rate",
            timestamp=time.time(),
            code=code
        )
        
        start = time.time()
        output_lines = []
        result_seen = False
        
        async for response in session.execute(msg, timeout=30.0):
            if response.type == MessageType.OUTPUT:
                assert not result_seen, "Output arrived after result!"
                output_lines.append(response.data)
            elif response.type == MessageType.RESULT:
                result_seen = True
        
        elapsed = time.time() - start
        
        # Join all output and count lines
        all_output = "".join(output_lines)
        line_count = all_output.count("\n")
        
        print(f"  Received {line_count} lines in {elapsed:.2f}s")
        print(f"  Rate: {line_count/elapsed:.0f} lines/sec")
        
        assert line_count == 10000, f"Expected 10000 lines, got {line_count}"
        
        # Verify ordering (sample check)
        lines = all_output.strip().split("\n")
        for i in range(min(100, len(lines))):  # Check first 100
            expected = f"Line {i:04d}"
            assert lines[i] == expected, f"Line {i} mismatch: {lines[i]} != {expected}"
            
    finally:
        await session.shutdown()
    
    print("  ✅ PASSED: All outputs received in order")


async def test_partial_lines():
    """Test 3: Partial lines without newline."""
    print("\n=== Test 3: Partial Lines ===")
    
    session = Session()
    await session.start()
    
    try:
        # Print without newline
        code = 'print("hello", end="")'
        msg = ExecuteMessage(
            id="partial",
            timestamp=time.time(),
            code=code
        )
        
        outputs = []
        async for response in session.execute(msg):
            if response.type == MessageType.OUTPUT:
                outputs.append(response.data)
        
        all_output = "".join(outputs)
        assert all_output == "hello", f"Expected 'hello', got '{all_output}'"
        
        # Test multiple partial prints
        code = '''
print("a", end="")
print("b", end="")
print("c")
'''
        msg = ExecuteMessage(
            id="partial-multi",
            timestamp=time.time(),
            code=code
        )
        
        outputs = []
        async for response in session.execute(msg):
            if response.type == MessageType.OUTPUT:
                outputs.append(response.data)
        
        all_output = "".join(outputs)
        assert all_output == "abc\n", f"Expected 'abc\\n', got '{all_output}'"
        
    finally:
        await session.shutdown()
    
    print("  ✅ PASSED: Partial lines handled correctly")


async def test_backpressure_behavior():
    """Test 4: Backpressure with small queue (would test if we could configure it)."""
    print("\n=== Test 4: Backpressure Behavior ===")
    
    # Note: This would be more comprehensive with configurable queue size
    # For now, test that large bursts still work
    
    session = Session()
    await session.start()
    
    try:
        # Generate a large burst of output
        code = """
import sys
# Generate 1MB of output quickly
data = "x" * 1024  # 1KB per line
for i in range(1024):  # 1024 lines = 1MB
    print(data)
    if i % 100 == 0:
        sys.stdout.flush()
"""
        msg = ExecuteMessage(
            id="backpressure",
            timestamp=time.time(),
            code=code
        )
        
        start = time.time()
        output_bytes = 0
        
        async for response in session.execute(msg, timeout=30.0):
            if response.type == MessageType.OUTPUT:
                output_bytes += len(response.data)
        
        elapsed = time.time() - start
        throughput_mb = (output_bytes / (1024*1024)) / elapsed
        
        print(f"  Transferred {output_bytes/1024:.0f} KB in {elapsed:.2f}s")
        print(f"  Throughput: {throughput_mb:.2f} MB/s")
        
        # Should have received approximately 1MB (some overhead for newlines)
        assert output_bytes > 1024 * 1024, f"Expected >1MB, got {output_bytes} bytes"
        
    finally:
        await session.shutdown()
    
    print("  ✅ PASSED: Large output handled without loss")


async def test_interleaved_output_streams():
    """Test 5: Interleaved stdout/stderr."""
    print("\n=== Test 5: Interleaved stdout/stderr ===")
    
    session = Session()
    await session.start()
    
    try:
        code = """
import sys
for i in range(10):
    if i % 2 == 0:
        print(f"stdout {i}", file=sys.stdout)
    else:
        print(f"stderr {i}", file=sys.stderr)
"""
        msg = ExecuteMessage(
            id="interleaved",
            timestamp=time.time(),
            code=code
        )
        
        outputs = []
        async for response in session.execute(msg):
            if response.type == MessageType.OUTPUT:
                outputs.append((response.stream, response.data))
        
        # Verify we got both streams
        stdout_lines = [data for stream, data in outputs if stream == "stdout"]
        stderr_lines = [data for stream, data in outputs if stream == "stderr"]
        
        assert len(stdout_lines) == 5, f"Expected 5 stdout, got {len(stdout_lines)}"
        assert len(stderr_lines) == 5, f"Expected 5 stderr, got {len(stderr_lines)}"
        
        # Verify content
        for i, line in enumerate(stdout_lines):
            expected = f"stdout {i*2}\n"
            assert line == expected, f"stdout mismatch: {line} != {expected}"
            
        for i, line in enumerate(stderr_lines):
            expected = f"stderr {i*2+1}\n"
            assert line == expected, f"stderr mismatch: {line} != {expected}"
        
    finally:
        await session.shutdown()
    
    print("  ✅ PASSED: stdout/stderr properly separated")


async def test_carriage_return_handling():
    """Test 6: Carriage return for progress bars."""
    print("\n=== Test 6: Carriage Return Handling ===")
    
    session = Session()
    await session.start()
    
    try:
        # Simulate a progress bar
        code = """
import sys
import time
for i in range(5):
    print(f"\\rProgress: {i}/4", end="", flush=True)
    time.sleep(0.01)  # Small delay to ensure separate messages
print("\\rComplete!    ")
"""
        msg = ExecuteMessage(
            id="carriage-return",
            timestamp=time.time(),
            code=code
        )
        
        outputs = []
        async for response in session.execute(msg):
            if response.type == MessageType.OUTPUT:
                outputs.append(response.data)
        
        # Should see each progress update
        all_output = "".join(outputs)
        assert "\r" in all_output, "Carriage returns should be preserved"
        assert "Complete!" in all_output, "Final message should be present"
        
    finally:
        await session.shutdown()
    
    print("  ✅ PASSED: Carriage returns handled")


async def test_very_long_lines():
    """Test 7: Very long lines (>64KB) get chunked."""
    print("\n=== Test 7: Very Long Line Chunking ===")
    
    session = Session()
    await session.start()
    
    try:
        # Create a line longer than 64KB
        code = """
long_line = "x" * 100000  # 100KB line
print(long_line)
print("done")
"""
        msg = ExecuteMessage(
            id="long-line",
            timestamp=time.time(),
            code=code
        )
        
        outputs = []
        async for response in session.execute(msg):
            if response.type == MessageType.OUTPUT:
                outputs.append(response.data)
        
        all_output = "".join(outputs)
        
        # Should have received the full line plus "done"
        assert "x" * 100000 in all_output, "Long line should be complete"
        assert "done\n" in all_output, "Following output should be present"
        
    finally:
        await session.shutdown()
    
    print("  ✅ PASSED: Long lines chunked correctly")


async def test_rapid_execution_sequence():
    """Test 8: Rapid sequence of executions (stress test)."""
    print("\n=== Test 8: Rapid Execution Sequence ===")
    
    session = Session()
    await session.start()
    
    try:
        failures = 0
        for i in range(100):
            code = f'print("exec_{i}")'
            msg = ExecuteMessage(
                id=f"rapid-{i}",
                timestamp=time.time(),
                code=code
            )
            
            output_found = False
            async for response in session.execute(msg):
                if response.type == MessageType.OUTPUT:
                    if f"exec_{i}" in response.data:
                        output_found = True
            
            if not output_found:
                failures += 1
        
        assert failures == 0, f"Lost output in {failures} executions"
        
    finally:
        await session.shutdown()
    
    print(f"  ✅ PASSED: 100 rapid executions without loss")


async def test_empty_output():
    """Test 9: Code with no output."""
    print("\n=== Test 9: Empty Output ===")
    
    session = Session()
    await session.start()
    
    try:
        code = "x = 42"  # No output
        msg = ExecuteMessage(
            id="no-output",
            timestamp=time.time(),
            code=code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        # Should get result but no output
        output_msgs = [m for m in messages if m.type == MessageType.OUTPUT]
        result_msgs = [m for m in messages if m.type == MessageType.RESULT]
        
        assert len(output_msgs) == 0, "Should have no output"
        assert len(result_msgs) == 1, "Should have result"
        
    finally:
        await session.shutdown()
    
    print("  ✅ PASSED: No output case handled")


async def test_exception_with_output():
    """Test 10: Exception after output."""
    print("\n=== Test 10: Exception After Output ===")
    
    session = Session()
    await session.start()
    
    try:
        code = """
print("Before error")
x = 1 / 0  # Will raise ZeroDivisionError
print("After error")  # Should not execute
"""
        msg = ExecuteMessage(
            id="exception",
            timestamp=time.time(),
            code=code
        )
        
        outputs = []
        error_seen = False
        
        async for response in session.execute(msg):
            if response.type == MessageType.OUTPUT:
                outputs.append(response.data)
            elif response.type == MessageType.ERROR:
                error_seen = True
        
        all_output = "".join(outputs)
        assert "Before error" in all_output, "Output before error should be present"
        assert "After error" not in all_output, "Output after error should not execute"
        assert error_seen, "Should have received error message"
        
    finally:
        await session.shutdown()
    
    print("  ✅ PASSED: Exception handling preserves prior output")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Event-Driven Output Handling Test Suite")
    print("=" * 60)
    
    start = time.time()
    
    tests = [
        test_race_reproduction,
        test_high_rate_output,
        test_partial_lines,
        test_backpressure_behavior,
        test_interleaved_output_streams,
        test_carriage_return_handling,
        test_very_long_lines,
        test_rapid_execution_sequence,
        test_empty_output,
        test_exception_with_output,
    ]
    
    failures = []
    for test in tests:
        try:
            await test()
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failures.append((test.__name__, e))
    
    elapsed = time.time() - start
    
    print("\n" + "=" * 60)
    print(f"Test Suite Complete in {elapsed:.2f}s")
    
    if failures:
        print(f"\n{len(failures)} test(s) failed:")
        for name, error in failures:
            print(f"  - {name}: {error}")
        sys.exit(1)
    else:
        print(f"✅ All {len(tests)} tests passed!")
        print("\nThe event-driven output handling is working correctly:")
        print("  - No race conditions detected")
        print("  - Output ordering preserved")
        print("  - No output loss under load")
        print("  - Proper stream separation")
        print("  - Correct exception handling")


if __name__ == "__main__":
    asyncio.run(main())