#!/usr/bin/env python3
"""
Test core execution capabilities of PyREPL3.
Validates basic functionality per unified planning requirements.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, MessageType, OutputMessage, ResultMessage, ErrorMessage

# Test results tracking
test_results: Dict[str, Any] = {}

async def measure_execution_time(session: Session, code: str) -> tuple[float, List[Any]]:
    """Execute code and measure time, returning elapsed time and messages."""
    start = time.perf_counter()
    
    msg = ExecuteMessage(
        id=f"test-{time.time()}",
        timestamp=time.time(),
        code=code
    )
    
    messages = []
    async for response in session.execute(msg):
        messages.append(response)
    
    elapsed = time.perf_counter() - start
    return elapsed * 1000, messages  # Convert to ms


async def test_simple_expression():
    """Test simple expression evaluation (target: <5ms)."""
    print("\n=== Test: Simple Expression (2+2) ===")
    session = Session()
    await session.start()
    
    try:
        elapsed_ms, messages = await measure_execution_time(session, "2 + 2")
        
        # Check for result
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        success = result_msg is not None and result_msg.value == 4
        
        print(f"✓ Expression evaluated: 2 + 2 = {result_msg.value if result_msg else 'ERROR'}")
        print(f"  Execution time: {elapsed_ms:.2f}ms (target: <5ms)")
        
        test_results["simple_expression"] = {
            "pass": success and elapsed_ms < 5,
            "time_ms": elapsed_ms,
            "value": result_msg.value if result_msg else None
        }
        
        return success and elapsed_ms < 5
        
    finally:
        await session.shutdown()


async def test_multiline_code():
    """Test multi-line code execution."""
    print("\n=== Test: Multi-line Code ===")
    session = Session()
    await session.start()
    
    code = """
x = 10
y = 20
result = x + y
print(f"Result: {result}")
result
"""
    
    try:
        elapsed_ms, messages = await measure_execution_time(session, code)
        
        # Check output and result
        output_msgs = [m for m in messages if isinstance(m, OutputMessage)]
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        
        has_output = any("Result: 30" in msg.data for msg in output_msgs)
        has_result = result_msg and result_msg.value == 30
        
        print(f"✓ Output captured: {'Yes' if has_output else 'No'}")
        print(f"✓ Result value: {result_msg.value if result_msg else 'None'}")
        print(f"  Execution time: {elapsed_ms:.2f}ms")
        
        test_results["multiline_code"] = {
            "pass": has_output and has_result,
            "time_ms": elapsed_ms,
            "has_output": has_output,
            "result": result_msg.value if result_msg else None
        }
        
        return has_output and has_result
        
    finally:
        await session.shutdown()


async def test_function_persistence():
    """Test function definitions persist in namespace."""
    print("\n=== Test: Function Persistence ===")
    session = Session()
    await session.start()
    
    try:
        # Define function
        code1 = """
def greet(name):
    return f"Hello, {name}!"
"""
        _, _ = await measure_execution_time(session, code1)
        
        # Use function in next execution
        code2 = "greet('World')"
        elapsed_ms, messages = await measure_execution_time(session, code2)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        success = result_msg and result_msg.value == "Hello, World!"
        
        print(f"✓ Function persisted: {'Yes' if success else 'No'}")
        print(f"  Result: {result_msg.value if result_msg else 'ERROR'}")
        
        test_results["function_persistence"] = {
            "pass": success,
            "result": result_msg.value if result_msg else None
        }
        
        return success
        
    finally:
        await session.shutdown()


async def test_class_persistence():
    """Test class definitions persist in namespace."""
    print("\n=== Test: Class Persistence ===")
    session = Session()
    await session.start()
    
    try:
        # Define class
        code1 = """
class Counter:
    def __init__(self):
        self.value = 0
    
    def increment(self):
        self.value += 1
        return self.value
"""
        _, _ = await measure_execution_time(session, code1)
        
        # Create instance
        code2 = "counter = Counter()"
        _, _ = await measure_execution_time(session, code2)
        
        # Use instance
        code3 = "counter.increment()"
        elapsed_ms, messages = await measure_execution_time(session, code3)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        success = result_msg and result_msg.value == 1
        
        print(f"✓ Class persisted: {'Yes' if success else 'No'}")
        print(f"  Counter value: {result_msg.value if result_msg else 'ERROR'}")
        
        test_results["class_persistence"] = {
            "pass": success,
            "value": result_msg.value if result_msg else None
        }
        
        return success
        
    finally:
        await session.shutdown()


async def test_import_persistence():
    """Test module imports persist."""
    print("\n=== Test: Import Persistence ===")
    session = Session()
    await session.start()
    
    try:
        # Import module
        code1 = "import math"
        _, _ = await measure_execution_time(session, code1)
        
        # Use imported module
        code2 = "math.pi"
        elapsed_ms, messages = await measure_execution_time(session, code2)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        success = result_msg and abs(result_msg.value - 3.14159) < 0.001
        
        print(f"✓ Import persisted: {'Yes' if success else 'No'}")
        print(f"  math.pi = {result_msg.value if result_msg else 'ERROR'}")
        
        test_results["import_persistence"] = {
            "pass": success,
            "value": result_msg.value if result_msg else None
        }
        
        return success
        
    finally:
        await session.shutdown()


async def test_global_variable_persistence():
    """Test global variables persist between executions."""
    print("\n=== Test: Global Variable Persistence ===")
    session = Session()
    await session.start()
    
    try:
        # Set global variable
        code1 = "global_counter = 0"
        _, _ = await measure_execution_time(session, code1)
        
        # Modify in function
        code2 = """
def increment_global():
    global global_counter
    global_counter += 1
    return global_counter

increment_global()
"""
        _, messages1 = await measure_execution_time(session, code2)
        
        # Check value
        code3 = "global_counter"
        _, messages2 = await measure_execution_time(session, code3)
        
        result1 = next((m for m in messages1 if isinstance(m, ResultMessage)), None)
        result2 = next((m for m in messages2 if isinstance(m, ResultMessage)), None)
        
        success = (result1 and result1.value == 1 and 
                  result2 and result2.value == 1)
        
        print(f"✓ Global persisted: {'Yes' if success else 'No'}")
        print(f"  Final value: {result2.value if result2 else 'ERROR'}")
        
        test_results["global_persistence"] = {
            "pass": success,
            "value": result2.value if result2 else None
        }
        
        return success
        
    finally:
        await session.shutdown()


async def test_error_handling():
    """Test error handling and recovery."""
    print("\n=== Test: Error Handling ===")
    session = Session()
    await session.start()
    
    try:
        # Cause syntax error
        code1 = "invalid syntax here"
        _, messages1 = await measure_execution_time(session, code1)
        
        error_msg = next((m for m in messages1 if isinstance(m, ErrorMessage)), None)
        has_syntax_error = error_msg and "SyntaxError" in error_msg.exception_type
        
        # Session should still work after error
        code2 = "1 + 1"
        _, messages2 = await measure_execution_time(session, code2)
        
        result_msg = next((m for m in messages2 if isinstance(m, ResultMessage)), None)
        recovers = result_msg and result_msg.value == 2
        
        print(f"✓ Syntax error caught: {'Yes' if has_syntax_error else 'No'}")
        print(f"✓ Session recovers: {'Yes' if recovers else 'No'}")
        
        test_results["error_handling"] = {
            "pass": has_syntax_error and recovers,
            "catches_errors": has_syntax_error,
            "recovers": recovers
        }
        
        return has_syntax_error and recovers
        
    finally:
        await session.shutdown()


async def test_performance_targets():
    """Test performance against unified planning targets."""
    print("\n=== Test: Performance Targets ===")
    session = Session()
    await session.start()
    
    try:
        # Test multiple simple expressions
        expressions = ["1+1", "2*3", "10/2", "100-50", "2**3"]
        times = []
        
        for expr in expressions:
            elapsed_ms, _ = await measure_execution_time(session, expr)
            times.append(elapsed_ms)
        
        avg_time = sum(times) / len(times)
        max_time = max(times)
        min_time = min(times)
        
        # Target: 2ms average, 5ms max
        meets_target = avg_time < 2 and max_time < 5
        
        print(f"  Average: {avg_time:.2f}ms (target: <2ms)")
        print(f"  Min: {min_time:.2f}ms")
        print(f"  Max: {max_time:.2f}ms (target: <5ms)")
        print(f"✓ Meets targets: {'Yes' if meets_target else 'No'}")
        
        test_results["performance"] = {
            "pass": meets_target,
            "avg_ms": avg_time,
            "min_ms": min_time,
            "max_ms": max_time
        }
        
        return meets_target
        
    finally:
        await session.shutdown()


async def main():
    """Run all core execution tests."""
    print("=" * 60)
    print("PYREPL3 FOUNDATION: CORE EXECUTION TESTS")
    print("=" * 60)
    
    tests = [
        ("Simple Expression", test_simple_expression),
        ("Multi-line Code", test_multiline_code),
        ("Function Persistence", test_function_persistence),
        ("Class Persistence", test_class_persistence),
        ("Import Persistence", test_import_persistence),
        ("Global Variables", test_global_variable_persistence),
        ("Error Handling", test_error_handling),
        ("Performance Targets", test_performance_targets),
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
        if "time_ms" in result:
            print(f"      Time: {result['time_ms']:.2f}ms")
        if "error" in result:
            print(f"      Error: {result['error']}")
    
    return passed == len(tests)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)