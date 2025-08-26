#!/usr/bin/env python3
"""
Debug script to investigate intermittent test_statement_blocks failure.
Runs the test multiple times with detailed logging to capture failure conditions.
"""

import asyncio
import sys
import time
import json
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, ResultMessage, OutputMessage, Message


async def run_statement_test_with_debug(iteration: int) -> Dict[str, Any]:
    """Run single test iteration with detailed debugging."""
    result = {
        "iteration": iteration,
        "start_time": time.time(),
        "messages": [],
        "output_text": "",
        "result_value": None,
        "passed": False,
        "error": None,
        "message_order": [],
        "timing": {}
    }
    
    session = Session()
    await session.start()
    
    try:
        # The problematic test code
        test_code = """
x = 10
y = 20
z = x + y
print(f"Sum: {z}")
"""
        
        msg = ExecuteMessage(
            id=f"test-{iteration}",
            timestamp=time.time(),
            code=test_code
        )
        
        # Track timing
        exec_start = time.time()
        
        messages = []
        message_times = []
        async for response in session.execute(msg):
            recv_time = time.time()
            messages.append(response)
            message_times.append((response.type, recv_time - exec_start))
            result["message_order"].append({
                "type": response.type,
                "time_offset": recv_time - exec_start,
                "id": response.id,
                "data": getattr(response, 'data', None) if isinstance(response, OutputMessage) else None,
                "value": getattr(response, 'value', None) if isinstance(response, ResultMessage) else None
            })
        
        exec_end = time.time()
        result["timing"]["execution_duration"] = exec_end - exec_start
        
        # Analyze messages
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        output_msgs = [m for m in messages if isinstance(m, OutputMessage)]
        
        # Capture all details
        result["messages"] = [
            {
                "type": m.type,
                "id": m.id,
                "data": getattr(m, 'data', None),
                "value": getattr(m, 'value', None),
                "stream": getattr(m, 'stream', None)
            } for m in messages
        ]
        
        output_text = "".join(msg.data for msg in output_msgs)
        result["output_text"] = output_text
        result["result_value"] = result_msg.value if result_msg else None
        
        # Check assertions
        assertion_checks = {
            "has_result_message": result_msg is not None,
            "result_is_none": result_msg.value is None if result_msg else True,
            "has_output_messages": len(output_msgs) > 0,
            "output_contains_sum": "Sum: 30" in output_text,
            "output_exact": output_text == "Sum: 30\n",
            "output_stripped": output_text.strip() == "Sum: 30"
        }
        result["assertion_checks"] = assertion_checks
        
        # Determine if test passed
        if result_msg and result_msg.value is not None:
            result["error"] = f"Result should be None, got {result_msg.value}"
        elif "Sum: 30" not in output_text:
            result["error"] = f"Output missing 'Sum: 30', got: {repr(output_text)}"
        else:
            result["passed"] = True
            
    except Exception as e:
        result["error"] = str(e)
        result["exception_type"] = type(e).__name__
        import traceback
        result["traceback"] = traceback.format_exc()
        
    finally:
        await session.shutdown()
        result["end_time"] = time.time()
        result["total_duration"] = result["end_time"] - result["start_time"]
        
    return result


async def run_multiple_tests(num_iterations: int = 20):
    """Run the test multiple times to catch intermittent failures."""
    print(f"Running {num_iterations} iterations to catch intermittent failures...")
    print("=" * 60)
    
    results = []
    failures = []
    
    for i in range(num_iterations):
        print(f"\nIteration {i+1}/{num_iterations}...", end=" ")
        result = await run_statement_test_with_debug(i)
        results.append(result)
        
        if result["passed"]:
            print("✓ PASSED")
        else:
            print(f"✗ FAILED: {result['error']}")
            failures.append(result)
    
    # Analyze results
    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    
    passed_count = sum(1 for r in results if r["passed"])
    failed_count = len(results) - passed_count
    
    print(f"Total runs: {num_iterations}")
    print(f"Passed: {passed_count} ({passed_count/num_iterations*100:.1f}%)")
    print(f"Failed: {failed_count} ({failed_count/num_iterations*100:.1f}%)")
    
    if failures:
        print("\nFAILURE PATTERNS:")
        print("-" * 40)
        
        # Group failures by error type
        error_groups = {}
        for failure in failures:
            error = failure["error"] or "Unknown error"
            if error not in error_groups:
                error_groups[error] = []
            error_groups[error].append(failure)
        
        for error, group in error_groups.items():
            print(f"\n{error}: {len(group)} occurrence(s)")
            
            # Show detailed info for first failure of this type
            first = group[0]
            print(f"  Iteration: {first['iteration']}")
            print(f"  Output text: {repr(first['output_text'])}")
            print(f"  Result value: {first['result_value']}")
            print(f"  Message order: {[m['type'] for m in first['message_order']]}")
            print(f"  Assertion checks: {first.get('assertion_checks', {})}")
            
        # Save detailed results for analysis
        with open("debug_results.json", "w") as f:
            json.dump(failures, f, indent=2, default=str)
        print(f"\nDetailed failure data saved to debug_results.json")
        
        # Check for timing patterns
        print("\nTIMING ANALYSIS:")
        print("-" * 40)
        
        all_durations = [r["timing"]["execution_duration"] for r in results if "timing" in r and "execution_duration" in r["timing"]]
        if all_durations:
            avg_duration = sum(all_durations) / len(all_durations)
            min_duration = min(all_durations)
            max_duration = max(all_durations)
            
            print(f"Execution duration - Avg: {avg_duration*1000:.2f}ms, Min: {min_duration*1000:.2f}ms, Max: {max_duration*1000:.2f}ms")
            
            # Check if failures correlate with fast executions (possible race condition)
            failed_durations = [r["timing"]["execution_duration"] for r in failures if "timing" in r and "execution_duration" in r["timing"]]
            if failed_durations:
                failed_avg = sum(failed_durations) / len(failed_durations)
                print(f"Failed tests avg duration: {failed_avg*1000:.2f}ms")
                if failed_avg < avg_duration * 0.8:
                    print("⚠️  Failures tend to happen on faster executions - possible race condition!")
    
    return results, failures


async def test_output_buffering():
    """Test specifically for output buffering issues."""
    print("\n" + "=" * 60)
    print("OUTPUT BUFFERING TEST")
    print("=" * 60)
    
    session = Session()
    await session.start()
    
    try:
        # Test with explicit flush
        test_cases = [
            ("No flush", 'print("Test", end=""); print(" message")'),
            ("With flush", 'import sys; print("Test", end=""); sys.stdout.flush(); print(" message")'),
            ("Multiple prints", 'print("Line1"); print("Line2"); print("Line3")'),
            ("Print with newline", 'print("Message\\n", end="")'),
        ]
        
        for name, code in test_cases:
            print(f"\nTesting: {name}")
            msg = ExecuteMessage(
                id=f"buffer-test-{name}",
                timestamp=time.time(),
                code=code
            )
            
            output_messages = []
            async for response in session.execute(msg):
                if isinstance(response, OutputMessage):
                    output_messages.append(response.data)
                    print(f"  Received output: {repr(response.data)}")
            
            combined = "".join(output_messages)
            print(f"  Combined output: {repr(combined)}")
            
    finally:
        await session.shutdown()


async def main():
    """Main debug routine."""
    print("INTERMITTENT FAILURE DEBUGGER")
    print("=" * 60)
    
    # Run multiple iterations
    results, failures = await run_multiple_tests(30)
    
    # Test output buffering specifically
    await test_output_buffering()
    
    # If we found failures, run a targeted test
    if failures:
        print("\n" + "=" * 60)
        print("TARGETED FAILURE REPRODUCTION")
        print("=" * 60)
        
        # Try to reproduce with minimal delay
        for i in range(5):
            print(f"\nRapid test {i+1}/5...")
            result = await run_statement_test_with_debug(100 + i)
            if not result["passed"]:
                print(f"Reproduced failure!")
                print(f"Messages received: {[m['type'] for m in result['message_order']]}")
                print(f"Output text: {repr(result['output_text'])}")
                break
            await asyncio.sleep(0.01)  # Minimal delay


if __name__ == "__main__":
    # Suppress debug logging for cleaner output
    import logging
    import structlog
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    )
    
    asyncio.run(main())