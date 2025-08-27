"""Integration tests for session management."""

import pytest
import asyncio
from tests.fixtures.sessions import create_session, SessionHelper
from tests.fixtures.messages import MessageFactory, assert_output_contains, assert_result_value
from src.protocol.messages import MessageType


@pytest.mark.integration
class TestSessionLifecycle:
    """Test session lifecycle management."""
    
    @pytest.mark.asyncio
    async def test_session_startup_and_shutdown(self):
        """Test that a session can start and shutdown cleanly."""
        async with create_session() as session:
            assert session.state.value == "ready"
        # Session should be shutdown after context exit
    
    @pytest.mark.asyncio
    async def test_session_with_warmup_code(self):
        """Test session startup with warmup code."""
        warmup = "x = 42\nprint('Warmed up')"
        async with create_session(warmup_code=warmup) as session:
            assert session.state.value == "ready"
            # Warmup should have executed
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_session_restart_after_crash(self):
        """Test session restart after worker crash."""
        async with create_session() as session:
            # Execute code that crashes the worker
            messages = await SessionHelper.execute_code(
                session, 
                "import sys; sys.exit(1)"
            )
            
            # Session should detect crash and be in error state
            assert any(msg.type == MessageType.ERROR for msg in messages)


@pytest.mark.integration
class TestSessionExecution:
    """Test code execution in sessions."""
    
    @pytest.mark.asyncio
    async def test_simple_execution(self):
        """Test executing simple Python code."""
        async with create_session() as session:
            messages = await SessionHelper.execute_code(session, "2 + 2")
            assert_result_value(messages, 4)
    
    @pytest.mark.asyncio
    async def test_print_output(self):
        """Test capturing print output."""
        async with create_session() as session:
            messages = await SessionHelper.execute_code(
                session,
                "print('Hello, World!')"
            )
            assert_output_contains(messages, "Hello, World!")
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error message generation."""
        async with create_session() as session:
            messages = await SessionHelper.execute_code(session, "1/0")
            
            errors = [m for m in messages if m.type == MessageType.ERROR]
            assert len(errors) == 1
            assert "ZeroDivisionError" in errors[0].exception_type
    
    @pytest.mark.asyncio
    async def test_multiline_execution(self):
        """Test executing multiline code."""
        code = """
x = 10
y = 20
result = x + y
print(f"Result: {result}")
result
"""
        async with create_session() as session:
            messages = await SessionHelper.execute_code(session, code)
            assert_output_contains(messages, "Result: 30")
            assert_result_value(messages, 30)
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_concurrent_executions(self):
        """Test multiple concurrent executions on same session."""
        async with create_session() as session:
            # Sessions should handle one execution at a time
            task1 = asyncio.create_task(
                SessionHelper.execute_code(session, "import time; time.sleep(0.1); 1")
            )
            task2 = asyncio.create_task(
                SessionHelper.execute_code(session, "2")
            )
            
            results = await asyncio.gather(task1, task2)
            assert len(results) == 2