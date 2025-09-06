"""End-to-end tests for complete execution flows."""

import pytest
import asyncio
from tests.fixtures.sessions import create_session, create_pool, SessionHelper
from tests.fixtures.messages import assert_output_contains, assert_result_value
from src.protocol.messages import MessageType


@pytest.mark.e2e
class TestCompleteExecutionFlow:
    """Test complete execution scenarios."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_interactive_session_flow(self):
        """Test a complete interactive session flow."""
        async with create_session() as session:
            # Step 1: Define a variable
            messages = await SessionHelper.execute_code(session, "name = 'Alice'")
            assert not any(m.type == MessageType.ERROR for m in messages)
            
            # Step 2: Use the variable
            messages = await SessionHelper.execute_code(
                session, 
                "print(f'Hello, {name}!')"
            )
            assert_output_contains(messages, "Hello, Alice!")
            
            # Step 3: Define a function
            messages = await SessionHelper.execute_code(session, """
def greet(person):
    return f"Welcome, {person}!"
""")
            assert not any(m.type == MessageType.ERROR for m in messages)
            
            # Step 4: Use the function
            messages = await SessionHelper.execute_code(session, "greet(name)")
            assert_result_value(messages, "Welcome, Alice!")
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_data_processing_flow(self):
        """Test a data processing workflow."""
        async with create_session() as session:
            # Create some data
            messages = await SessionHelper.execute_code(session, """
data = [1, 2, 3, 4, 5]
squares = [x**2 for x in data]
print(f"Original: {data}")
print(f"Squares: {squares}")
sum(squares)
""")
            assert_output_contains(messages, "Original: [1, 2, 3, 4, 5]")
            assert_output_contains(messages, "Squares: [1, 4, 9, 16, 25]")
            assert_result_value(messages, 55)
    
    @pytest.mark.asyncio
    @pytest.mark.slow 
    async def test_exception_recovery_flow(self):
        """Test recovery from exceptions."""
        async with create_session() as session:
            # Cause an error
            messages = await SessionHelper.execute_code(session, "x = 1/0")
            assert any(m.type == MessageType.ERROR for m in messages)
            
            # Verify session still works
            messages = await SessionHelper.execute_code(session, "y = 10")
            assert not any(m.type == MessageType.ERROR for m in messages)
            
            # Use the variable
            messages = await SessionHelper.execute_code(session, "y * 2")
            assert_result_value(messages, 20)


@pytest.mark.e2e
class TestPoolExecutionFlow:
    """Test execution flows using session pools."""
    # Phase 3: pool/reuse/concurrency is out-of-scope for Phase 2 local-mode stabilization
    # Marking xfail to reflect deferral and avoid competing reader patterns in tests
    pytestmark = pytest.mark.xfail(
        reason="Deferred to Phase 3: pool/perf/concurrency hardening",
        strict=False,
    )
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_pool_session_reuse(self):
        """Test that pool reuses sessions efficiently."""
        async with create_pool(min_idle=2, max_sessions=4) as pool:
            # Get a session and use it
            async with pool.acquire() as session:
                messages = await SessionHelper.execute_code(session, "x = 100")
                assert not any(m.type == MessageType.ERROR for m in messages)
            
            # Get another session (should be reused)
            async with pool.acquire() as session:
                # Variable should not persist (different session)
                messages = await SessionHelper.execute_code(session, """
try:
    print(x)
except NameError:
    print("x not defined")
""")
                assert_output_contains(messages, "x not defined")
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_concurrent_pool_executions(self):
        """Test concurrent executions using pool."""
        async with create_pool(min_idle=2, max_sessions=4) as pool:
            async def execute_task(task_id: int):
                async with pool.acquire() as session:
                    code = f"print('Task {task_id}'); {task_id} * 10"
                    messages = await SessionHelper.execute_code(session, code)
                    assert_output_contains(messages, f"Task {task_id}")
                    return messages
            
            # Run multiple tasks concurrently
            tasks = [execute_task(i) for i in range(4)]
            results = await asyncio.gather(*tasks)
            assert len(results) == 4
