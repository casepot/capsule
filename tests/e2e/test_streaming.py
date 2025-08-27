#!/usr/bin/env python3
"""
Test output streaming performance and capabilities.
Target: <10ms latency from print() to client receipt (per unified planning).
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType, OutputMessage

# Test results tracking
test_results: Dict[str, Any] = {}


async def test_basic_output_streaming():
    """Test basic output streaming with timing."""
    print("\n=== Test: Basic Output Streaming ===")
    session = Session()
    await session.start()
    
    try:
        code = """
import time
start = time.perf_counter()
print("Hello, World!")
elapsed = (time.perf_counter() - start) * 1000
print(f"Print took: {elapsed:.2f}ms")
"""
        
        msg = ExecuteMessage(
            id=f"test-{time.time()}",
            timestamp=time.time(),
            code=code
        )
        
        output_messages = []
        first_output_time = None
        start_time = time.perf_counter()
        
        async for response in session.execute(msg):
            if isinstance(response, OutputMessage):
                if first_output_time is None:
                    first_output_time = time.perf_counter()
                output_messages.append(response)
        
        if first_output_time:
            latency = (first_output_time - start_time) * 1000
            print(f"  First output latency: {latency:.2f}ms (target: <10ms)")
            
            # Check output content
            combined_output = "".join(msg.data for msg in output_messages)
            has_hello = "Hello, World!" in combined_output
            
            test_results["basic_streaming"] = {
                "pass": has_hello and latency < 10,
                "latency_ms": latency,
                "output_count": len(output_messages)
            }
            
            print(f"✓ Output captured: {'Yes' if has_hello else 'No'}")
            print(f"  Messages received: {len(output_messages)}")
            
            return has_hello and latency < 10
        else:
            test_results["basic_streaming"] = {"pass": False, "error": "No output"}
            return False
            
    finally:
        await session.shutdown()


async def test_stdout_stderr_separation():
    """Test stdout and stderr stream separation."""
    print("\n=== Test: stdout/stderr Separation ===")
    session = Session()
    await session.start()
    
    try:
        code = """
import sys
print("To stdout", file=sys.stdout)
print("To stderr", file=sys.stderr)
print("Another stdout")
"""
        
        msg = ExecuteMessage(
            id=f"test-{time.time()}",
            timestamp=time.time(),
            code=code
        )
        
        stdout_messages = []
        stderr_messages = []
        
        async for response in session.execute(msg):
            if isinstance(response, OutputMessage):
                if response.stream == "stdout":
                    stdout_messages.append(response.data)
                elif response.stream == "stderr":
                    stderr_messages.append(response.data)
        
        stdout_text = "".join(stdout_messages)
        stderr_text = "".join(stderr_messages)
        
        has_correct_stdout = "To stdout" in stdout_text and "Another stdout" in stdout_text
        has_correct_stderr = "To stderr" in stderr_text
        separated = "To stderr" not in stdout_text and "To stdout" not in stderr_text
        
        print(f"  stdout messages: {len(stdout_messages)}")
        print(f"  stderr messages: {len(stderr_messages)}")
        print(f"✓ Streams separated: {'Yes' if separated else 'No'}")
        
        test_results["stream_separation"] = {
            "pass": has_correct_stdout and has_correct_stderr and separated,
            "stdout_count": len(stdout_messages),
            "stderr_count": len(stderr_messages)
        }
        
        return has_correct_stdout and has_correct_stderr and separated
        
    finally:
        await session.shutdown()


async def test_output_ordering():
    """Test that output order is preserved."""
    print("\n=== Test: Output Order Preservation ===")
    session = Session()
    await session.start()
    
    try:
        code = """
for i in range(5):
    print(f"Line {i}")
"""
        
        msg = ExecuteMessage(
            id=f"test-{time.time()}",
            timestamp=time.time(),
            code=code
        )
        
        output_lines = []
        async for response in session.execute(msg):
            if isinstance(response, OutputMessage):
                output_lines.append(response.data.strip())
        
        # Check ordering
        expected = [f"Line {i}" for i in range(5)]
        actual = [line for line in output_lines if line]  # Filter empty lines
        
        order_preserved = actual == expected
        
        print(f"  Expected: {expected}")
        print(f"  Actual: {actual}")
        print(f"✓ Order preserved: {'Yes' if order_preserved else 'No'}")
        
        test_results["output_ordering"] = {
            "pass": order_preserved,
            "lines": len(actual)
        }
        
        return order_preserved
        
    finally:
        await session.shutdown()


async def test_large_output():
    """Test handling of large output (>1MB)."""
    print("\n=== Test: Large Output Handling ===")
    session = Session()
    await session.start()
    
    try:
        # Generate ~1MB of output
        code = """
import sys
chunk = "x" * 1024  # 1KB chunk
for i in range(1024):  # 1024 * 1KB = 1MB
    print(chunk, end='')
    if i % 100 == 0:
        sys.stdout.flush()
print("\\nDONE")
"""
        
        msg = ExecuteMessage(
            id=f"test-{time.time()}",
            timestamp=time.time(),
            code=code
        )
        
        total_bytes = 0
        message_count = 0
        start_time = time.perf_counter()
        
        async for response in session.execute(msg):
            if isinstance(response, OutputMessage):
                total_bytes += len(response.data)
                message_count += 1
        
        elapsed = time.perf_counter() - start_time
        throughput_mbps = (total_bytes / 1024 / 1024) / elapsed if elapsed > 0 else 0
        
        success = total_bytes >= 1024 * 1024  # At least 1MB
        
        print(f"  Total output: {total_bytes / 1024:.1f}KB")
        print(f"  Messages: {message_count}")
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Throughput: {throughput_mbps:.2f}MB/s (target: >10MB/s)")
        print(f"✓ Large output handled: {'Yes' if success else 'No'}")
        
        test_results["large_output"] = {
            "pass": success and throughput_mbps > 10,
            "total_bytes": total_bytes,
            "throughput_mbps": throughput_mbps
        }
        
        return success
        
    finally:
        await session.shutdown()


async def test_unicode_output():
    """Test Unicode and special character handling."""
    print("\n=== Test: Unicode Output ===")
    session = Session()
    await session.start()
    
    try:
        code = """
print("ASCII: Hello")
print("Emoji: 🎉 🐍 ✨")
print("Chinese: 你好世界")
print("Arabic: مرحبا بالعالم")
print("Math: ∑ ∫ ∞ π")
"""
        
        msg = ExecuteMessage(
            id=f"test-{time.time()}",
            timestamp=time.time(),
            code=code
        )
        
        output_messages = []
        async for response in session.execute(msg):
            if isinstance(response, OutputMessage):
                output_messages.append(response.data)
        
        combined = "".join(output_messages)
        
        # Check for various Unicode content
        has_emoji = "🎉" in combined and "🐍" in combined
        has_chinese = "你好世界" in combined
        has_arabic = "مرحبا" in combined
        has_math = "∑" in combined and "π" in combined
        
        all_unicode = has_emoji and has_chinese and has_arabic and has_math
        
        print(f"  Emoji: {'✓' if has_emoji else '✗'}")
        print(f"  Chinese: {'✓' if has_chinese else '✗'}")
        print(f"  Arabic: {'✓' if has_arabic else '✗'}")
        print(f"  Math symbols: {'✓' if has_math else '✗'}")
        print(f"✓ Unicode handled: {'Yes' if all_unicode else 'No'}")
        
        test_results["unicode_output"] = {
            "pass": all_unicode,
            "emoji": has_emoji,
            "chinese": has_chinese,
            "arabic": has_arabic,
            "math": has_math
        }
        
        return all_unicode
        
    finally:
        await session.shutdown()


async def test_streaming_latency_detailed():
    """Test detailed streaming latency for multiple prints."""
    print("\n=== Test: Detailed Streaming Latency ===")
    session = Session()
    await session.start()
    
    try:
        code = """
import time
for i in range(5):
    start = time.perf_counter()
    print(f"Message {i}")
    # Small delay to separate messages
    time.sleep(0.001)
"""
        
        msg = ExecuteMessage(
            id=f"test-{time.time()}",
            timestamp=time.time(),
            code=code
        )
        
        latencies = []
        start_time = time.perf_counter()
        last_time = start_time
        
        async for response in session.execute(msg):
            if isinstance(response, OutputMessage):
                current_time = time.perf_counter()
                latency = (current_time - last_time) * 1000
                latencies.append(latency)
                last_time = current_time
        
        if latencies:
            # First latency is from execution start
            first_latency = latencies[0]
            # Rest are inter-message latencies
            avg_latency = sum(latencies[1:]) / len(latencies[1:]) if len(latencies) > 1 else first_latency
            max_latency = max(latencies)
            
            print(f"  First message: {first_latency:.2f}ms")
            print(f"  Average latency: {avg_latency:.2f}ms")
            print(f"  Max latency: {max_latency:.2f}ms")
            print(f"✓ All under 10ms: {'Yes' if max_latency < 10 else 'No'}")
            
            test_results["streaming_latency"] = {
                "pass": max_latency < 10,
                "first_ms": first_latency,
                "avg_ms": avg_latency,
                "max_ms": max_latency
            }
            
            return max_latency < 10
        
        test_results["streaming_latency"] = {"pass": False, "error": "No output"}
        return False
        
    finally:
        await session.shutdown()


async def test_output_buffering():
    """Test output buffering behavior."""
    print("\n=== Test: Output Buffering ===")
    session = Session()
    await session.start()
    
    try:
        code = """
import sys
# Write without newline
sys.stdout.write("Part1")
sys.stdout.write("Part2")
sys.stdout.write("Part3\\n")  # Now flush with newline
sys.stdout.write("Part4")
sys.stdout.flush()  # Force flush
"""
        
        msg = ExecuteMessage(
            id=f"test-{time.time()}",
            timestamp=time.time(),
            code=code
        )
        
        messages = []
        async for response in session.execute(msg):
            if isinstance(response, OutputMessage):
                messages.append(response.data)
        
        # Check buffering behavior
        combined = "".join(messages)
        has_all_parts = all(f"Part{i}" in combined for i in range(1, 5))
        
        print(f"  Messages received: {len(messages)}")
        print(f"  Output: {repr(combined)}")
        print(f"✓ All parts received: {'Yes' if has_all_parts else 'No'}")
        
        test_results["output_buffering"] = {
            "pass": has_all_parts,
            "message_count": len(messages),
            "combined_length": len(combined)
        }
        
        return has_all_parts
        
    finally:
        await session.shutdown()


async def main():
    """Run all streaming output tests."""
    print("=" * 60)
    print("PYREPL3 FOUNDATION: STREAMING OUTPUT TESTS")
    print("=" * 60)
    
    tests = [
        ("Basic Streaming", test_basic_output_streaming),
        ("Stream Separation", test_stdout_stderr_separation),
        ("Output Ordering", test_output_ordering),
        ("Large Output", test_large_output),
        ("Unicode Output", test_unicode_output),
        ("Streaming Latency", test_streaming_latency_detailed),
        ("Output Buffering", test_output_buffering),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {name} crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
            test_results[name.lower().replace(" ", "_")] = {
                "pass": False,
                "error": str(e)
            }
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")
    
    # Detailed results
    print("\nDetailed Results:")
    for test_name, result in test_results.items():
        status = "✅" if result.get("pass") else "❌"
        print(f"  {status} {test_name}")
        if "latency_ms" in result:
            print(f"      Latency: {result['latency_ms']:.2f}ms")
        if "throughput_mbps" in result:
            print(f"      Throughput: {result['throughput_mbps']:.2f}MB/s")
        if "error" in result:
            print(f"      Error: {result['error']}")
    
    # Key metrics
    print("\nKey Metrics vs Targets:")
    if "basic_streaming" in test_results:
        lat = test_results["basic_streaming"].get("latency_ms", "N/A")
        print(f"  Output latency: {lat:.2f}ms (target: <10ms)" if isinstance(lat, (int, float)) else f"  Output latency: {lat}")
    if "large_output" in test_results:
        tput = test_results["large_output"].get("throughput_mbps", "N/A")
        print(f"  Throughput: {tput:.2f}MB/s (target: >10MB/s)" if isinstance(tput, (int, float)) else f"  Throughput: {tput}")
    
    return passed == len(tests)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)