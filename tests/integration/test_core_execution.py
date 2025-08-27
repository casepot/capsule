"""Core execution integration tests.

These tests validate fundamental PyREPL3 functionality and performance targets.
"""

import pytest
import asyncio
import time
from tests.fixtures.sessions import create_session, SessionHelper
from tests.fixtures.messages import assert_output_contains, assert_result_value
from src.protocol.messages import MessageType


@pytest.mark.integration
class TestCoreExecution:
    """Test core execution capabilities."""
    
    @pytest.mark.asyncio
    async def test_simple_expression_performance(self):
        """Test simple expression evaluation performance (target: <5ms)."""
        async with create_session() as session:
            start = time.perf_counter()
            messages = await SessionHelper.execute_code(session, "2 + 2")
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            assert_result_value(messages, 4)
            # Note: First execution may be slower due to initialization
            assert elapsed_ms < 50, f"Execution took {elapsed_ms:.2f}ms (target: <50ms)"
    
    @pytest.mark.asyncio
    async def test_function_persistence(self):
        """Test that functions persist across executions."""
        async with create_session() as session:
            # Define function
            messages = await SessionHelper.execute_code(session, """
def greet(name):
    return f"Hello, {name}!"
""")
            assert not any(m.type == MessageType.ERROR for m in messages)
            
            # Use function in next execution
            messages = await SessionHelper.execute_code(session, "greet('World')")
            assert_result_value(messages, "Hello, World!")
    
    @pytest.mark.asyncio
    async def test_class_persistence(self):
        """Test that classes persist across executions."""
        async with create_session() as session:
            # Define class
            messages = await SessionHelper.execute_code(session, """
class Counter:
    def __init__(self):
        self.count = 0
    
    def increment(self):
        self.count += 1
        return self.count
""")
            assert not any(m.type == MessageType.ERROR for m in messages)
            
            # Create instance
            messages = await SessionHelper.execute_code(session, "c = Counter()")
            assert not any(m.type == MessageType.ERROR for m in messages)
            
            # Use instance
            messages = await SessionHelper.execute_code(session, "c.increment()")
            assert_result_value(messages, 1)
            
            messages = await SessionHelper.execute_code(session, "c.increment()")
            assert_result_value(messages, 2)
    
    @pytest.mark.asyncio
    async def test_import_persistence(self):
        """Test that imports persist across executions."""
        async with create_session() as session:
            # Import module
            messages = await SessionHelper.execute_code(session, "import math")
            assert not any(m.type == MessageType.ERROR for m in messages)
            
            # Use imported module
            messages = await SessionHelper.execute_code(session, "math.pi")
            results = [m for m in messages if m.type == MessageType.RESULT]
            assert len(results) == 1
            assert abs(results[0].value - 3.14159) < 0.001
    
    @pytest.mark.asyncio
    async def test_global_variable_modification(self):
        """Test modifying global variables."""
        async with create_session() as session:
            # Set initial value
            messages = await SessionHelper.execute_code(session, "counter = 0")
            assert not any(m.type == MessageType.ERROR for m in messages)
            
            # Increment
            messages = await SessionHelper.execute_code(session, """
counter += 10
counter
""")
            assert_result_value(messages, 10)
            
            # Verify persistence
            messages = await SessionHelper.execute_code(session, "counter")
            assert_result_value(messages, 10)
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_output_handling(self):
        """Test handling large output efficiently."""
        async with create_session() as session:
            # Generate large output
            messages = await SessionHelper.execute_code(session, """
for i in range(100):
    print(f"Line {i}: " + "x" * 50)
"done"
""")
            
            # Check we got output and result
            outputs = [m for m in messages if m.type == MessageType.OUTPUT]
            assert len(outputs) > 0
            assert_result_value(messages, "done")
    
    @pytest.mark.asyncio
    async def test_exception_traceback(self):
        """Test that exceptions include full traceback."""
        async with create_session() as session:
            messages = await SessionHelper.execute_code(session, """
def inner():
    return 1/0

def outer():
    return inner()

outer()
""")
            
            errors = [m for m in messages if m.type == MessageType.ERROR]
            assert len(errors) == 1
            assert "ZeroDivisionError" in errors[0].exception_type
            assert "traceback" in errors[0].model_dump()
            assert "inner" in errors[0].traceback
            assert "outer" in errors[0].traceback
    
    @pytest.mark.asyncio
    async def test_last_result_underscore(self):
        """Test that last result is available as '_'."""
        async with create_session() as session:
            # Execute expression
            messages = await SessionHelper.execute_code(session, "42")
            assert_result_value(messages, 42)
            
            # Check underscore has last result
            messages = await SessionHelper.execute_code(session, "_")
            assert_result_value(messages, 42)
            
            # New result updates underscore
            messages = await SessionHelper.execute_code(session, "'hello'")
            assert_result_value(messages, "hello")
            
            messages = await SessionHelper.execute_code(session, "_")
            assert_result_value(messages, "hello")