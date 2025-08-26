#!/usr/bin/env python3
"""
Test single-pass evaluation to ensure expressions with side effects run exactly once.

This test suite validates that the fix for double execution is working correctly.
The bug was that code like `f()` would execute twice:
1. Once during exec()
2. Once during eval() to capture the result

The fix ensures code runs exactly once while still capturing expression results.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage, ResultMessage, OutputMessage


async def test_expression_with_side_effects():
    """Test that expressions with side effects execute exactly once."""
    print("\n=== Test: Expression with Side Effects ===")
    session = Session()
    await session.start()
    
    try:
        # Setup: Create a counter that tracks function calls
        setup_code = """
calls = 0

def increment_and_return():
    global calls
    calls += 1
    print(f"Function called: {calls} time(s)")
    return calls
"""
        msg = ExecuteMessage(
            id="setup",
            timestamp=time.time(),
            code=setup_code
        )
        async for response in session.execute(msg):
            pass  # Setup complete
        
        # Test: Call the function as an expression
        test_code = "increment_and_return()"
        msg = ExecuteMessage(
            id="test-expr",
            timestamp=time.time(),
            code=test_code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        # Verify result
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        output_msgs = [m for m in messages if isinstance(m, OutputMessage)]
        
        # Check that function was called exactly once
        assert result_msg is not None, "Expression should return a result"
        assert result_msg.value == 1, f"Expected result 1, got {result_msg.value}"
        
        # Verify output shows single call
        output_text = "".join(msg.data for msg in output_msgs)
        assert "Function called: 1 time(s)" in output_text
        assert "Function called: 2 time(s)" not in output_text
        
        # Double-check: Verify counter value
        verify_code = "calls"
        msg = ExecuteMessage(
            id="verify",
            timestamp=time.time(),
            code=verify_code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        assert result_msg.value == 1, f"Counter should be 1, but got {result_msg.value}"
        
        print("✓ Expression with side effects executed exactly once")
        return True
        
    finally:
        await session.shutdown()


async def test_list_append_side_effect():
    """Test that list operations with side effects happen exactly once."""
    print("\n=== Test: List Append Side Effect ===")
    session = Session()
    await session.start()
    
    try:
        # Setup list and function
        setup_code = """
x = [0]
def append_and_return():
    x.append(len(x))
    return len(x)
"""
        msg = ExecuteMessage(
            id="setup-list",
            timestamp=time.time(),
            code=setup_code
        )
        async for response in session.execute(msg):
            pass
        
        # Test: Call function as pure expression (no semicolons)
        test_code = "append_and_return()"
        msg = ExecuteMessage(
            id="test-list",
            timestamp=time.time(),
            code=test_code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        assert result_msg is not None, "Expression should return a result"
        assert result_msg.value == 2, f"Expected length 2 (called once), got {result_msg.value}"
        
        # Verify list contents - should have exactly one append
        verify_code = "x"
        msg = ExecuteMessage(
            id="verify-list",
            timestamp=time.time(),
            code=verify_code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        assert result_msg.value == [0, 1], f"Expected [0, 1] (one append), got {result_msg.value}"
        
        print("✓ List append executed exactly once")
        return True
        
    finally:
        await session.shutdown()


async def test_pure_expression():
    """Test that pure expressions still return results."""
    print("\n=== Test: Pure Expression ===")
    session = Session()
    await session.start()
    
    try:
        # Test various pure expressions
        test_cases = [
            ("2 + 2", 4),
            ("'hello' + ' world'", 'hello world'),
            ("[1, 2, 3][-1]", 3),
            ("len('test')", 4),
            ("True and False", False),
        ]
        
        for code, expected in test_cases:
            msg = ExecuteMessage(
                id=f"test-{code}",
                timestamp=time.time(),
                code=code
            )
            
            messages = []
            async for response in session.execute(msg):
                messages.append(response)
            
            result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
            assert result_msg is not None, f"Expression '{code}' should return a result"
            assert result_msg.value == expected, f"Expected {expected}, got {result_msg.value}"
            print(f"  ✓ {code} = {result_msg.value}")
        
        print("✓ All pure expressions returned correct results")
        return True
        
    finally:
        await session.shutdown()


async def test_statement_blocks():
    """Test that statement blocks don't return results."""
    print("\n=== Test: Statement Blocks ===")
    session = Session()
    await session.start()
    
    try:
        # Test: Multi-line statements
        test_code = """
x = 10
y = 20
z = x + y
print(f"Sum: {z}")
"""
        msg = ExecuteMessage(
            id="test-statements",
            timestamp=time.time(),
            code=test_code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        output_msgs = [m for m in messages if isinstance(m, OutputMessage)]
        
        # Multi-line code is treated as statements (exec mode), so result should be None
        # This is the correct behavior - only pure single expressions return results
        if result_msg:
            assert result_msg.value is None, \
                f"Statement block should return None, got {result_msg.value}"
        
        # But output should still work
        output_text = "".join(msg.data for msg in output_msgs)
        assert "Sum: 30" in output_text, f"Output should contain 'Sum: 30', got {repr(output_text)}"
        
        print("✓ Statement blocks execute without returning results")
        return True
        
    finally:
        await session.shutdown()


async def test_multiline_with_last_expression():
    """Test behavior of multi-line code ending with an expression."""
    print("\n=== Test: Multi-line with Last Expression ===")
    session = Session()
    await session.start()
    
    try:
        # Test: Statements followed by expression on last line
        test_code = """x = 5
y = 10
x + y"""
        
        msg = ExecuteMessage(
            id="test-multiline",
            timestamp=time.time(),
            code=test_code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        
        # Multi-line code cannot be parsed as a single expression, so it's exec'd as statements
        # This matches standard Python REPL behavior - only single-line pure expressions return values
        if result_msg:
            assert result_msg.value is None, \
                f"Multi-line code should return None, got {result_msg.value}"
        
        # But the variables should be set
        verify_code = "x, y"
        msg = ExecuteMessage(
            id="verify-vars",
            timestamp=time.time(),
            code=verify_code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        # The tuple may be serialized as a list
        assert result_msg.value in [(5, 10), [5, 10]], f"Expected (5, 10) or [5, 10], got {result_msg.value}"
        
        print("✓ Multi-line code with last expression handled correctly")
        return True
        
    finally:
        await session.shutdown()


async def test_global_counter_increment():
    """Test that global counter increments happen exactly once."""
    print("\n=== Test: Global Counter Increment ===")
    session = Session()
    await session.start()
    
    try:
        # Setup global counter
        setup_code = "counter = 0"
        msg = ExecuteMessage(
            id="setup-counter",
            timestamp=time.time(),
            code=setup_code
        )
        async for response in session.execute(msg):
            pass
        
        # Test: Increment expression
        test_code = """
def increment():
    global counter
    counter += 1
    return counter

increment()
"""
        msg = ExecuteMessage(
            id="test-increment",
            timestamp=time.time(),
            code=test_code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        
        # Since this is multi-line, it's treated as statements, no result
        assert result_msg is None or result_msg.value is None
        
        # But counter should be incremented exactly once
        verify_code = "counter"
        msg = ExecuteMessage(
            id="verify-counter",
            timestamp=time.time(),
            code=verify_code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        assert result_msg.value == 1, f"Counter should be 1, got {result_msg.value}"
        
        # Test single-line increment call
        test_code2 = "increment()"
        msg = ExecuteMessage(
            id="test-single-increment",
            timestamp=time.time(),
            code=test_code2
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        assert result_msg is not None, "Single expression should return result"
        assert result_msg.value == 2, f"Expected 2, got {result_msg.value}"
        
        # Verify final counter value
        verify_code = "counter"
        msg = ExecuteMessage(
            id="verify-final",
            timestamp=time.time(),
            code=verify_code
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        
        result_msg = next((m for m in messages if isinstance(m, ResultMessage)), None)
        assert result_msg.value == 2, f"Final counter should be 2, got {result_msg.value}"
        
        print("✓ Global counter increments happen exactly once")
        return True
        
    finally:
        await session.shutdown()


async def run_all_tests():
    """Run all single-pass evaluation tests."""
    print("\n" + "="*60)
    print("SINGLE-PASS EVALUATION TEST SUITE")
    print("="*60)
    
    tests = [
        test_expression_with_side_effects,
        test_list_append_side_effect,
        test_pure_expression,
        test_statement_blocks,
        test_multiline_with_last_expression,
        test_global_counter_increment,
    ]
    
    results = []
    for test_func in tests:
        try:
            result = await test_func()
            results.append((test_func.__name__, result))
        except Exception as e:
            print(f"✗ {test_func.__name__} failed: {e}")
            results.append((test_func.__name__, False))
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)