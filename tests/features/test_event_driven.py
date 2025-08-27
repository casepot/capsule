"""Tests for event-driven cancellation pattern."""

import asyncio
import pytest
import time
import uuid
from typing import List

from src.protocol.messages import (
    ExecuteMessage,
    Message,
    MessageType,
    OutputMessage,
    ErrorMessage,
    ResultMessage,
)
from src.session.manager import Session
from src.session.config import SessionConfig


class TestEventDrivenCancellation:
    """Test event-driven cancellation mechanism."""
    
    async def _collect_messages(self, session: Session, execute_msg: ExecuteMessage) -> List[Message]:
        """Helper to collect all messages from an execution."""
        messages = []
        try:
            async for msg in session.execute(execute_msg):
                messages.append(msg)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        return messages
    
    @pytest.mark.asyncio
    async def test_immediate_cancellation_response(self):
        """Test that cancellation is immediate (<50ms)."""
        session = Session()
        await session.start()
        
        try:
            # Start long-running execution
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
import time
print("Starting long task")
time.sleep(30)  # Will be cancelled before completion
print("Should not reach here")
""",
            )
            
            # Start execution in background
            task = asyncio.create_task(self._collect_messages(session, execute_msg))
            
            # Wait for execution to start
            await asyncio.sleep(0.1)
            
            # Measure cancellation latency
            t0 = time.perf_counter()
            await session.terminate()
            
            # Wait for task to complete (should be fast due to cancellation)
            await asyncio.wait_for(task, timeout=0.1)
            
            cancel_latency = time.perf_counter() - t0
            assert cancel_latency < 0.05, f"Cancellation took {cancel_latency}s, expected <50ms"
            
        finally:
            await session.terminate()
    
    @pytest.mark.asyncio
    async def test_cancel_event_triggers_on_shutdown(self):
        """Test that cancel event is properly triggered on shutdown."""
        config = SessionConfig(enable_metrics=True)
        session = Session(config=config)
        await session.start()
        
        try:
            # Start a long-running execution
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
import time
for i in range(100):
    time.sleep(0.1)
    print(f"Iteration {i}")
""",
            )
            
            # Start execution
            task = asyncio.create_task(self._collect_messages(session, execute_msg))
            
            # Wait a bit then shutdown
            await asyncio.sleep(0.5)
            await session.shutdown("Test shutdown")
            
            # Execution should be cancelled
            messages = await task
            
            # Check that cancel event was triggered
            assert session._metrics['cancel_event_triggers'] > 0, \
                "Cancel event should have been triggered during shutdown"
            
        finally:
            await session.terminate()
    
    @pytest.mark.asyncio
    async def test_timeout_behavior(self):
        """Test that timeout behavior works correctly."""
        session = Session()
        await session.start()
        
        try:
            # Execute code with a short timeout
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
import time
time.sleep(10)  # Longer than timeout
print("Should not reach here")
""",
            )
            
            # Should timeout
            with pytest.raises(asyncio.TimeoutError):
                messages = []
                async for msg in session.execute(execute_msg, timeout=1.0):
                    messages.append(msg)
            
        finally:
            await session.terminate()
    
    @pytest.mark.asyncio
    async def test_receive_message_cancellation(self):
        """Test that receive_message also uses cancellable wait."""
        session = Session()
        await session.start()
        
        try:
            # Start waiting for a message that won't come
            receive_task = asyncio.create_task(
                session.receive_message(timeout=30.0)
            )
            
            # Wait a bit then terminate
            await asyncio.sleep(0.1)
            
            t0 = time.perf_counter()
            await session.terminate()
            
            # Should cancel quickly
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(receive_task, timeout=0.1)
            
            cancel_latency = time.perf_counter() - t0
            assert cancel_latency < 0.05, \
                f"receive_message cancellation took {cancel_latency}s, expected <50ms"
            
        finally:
            await session.terminate()
    
    @pytest.mark.asyncio
    async def test_no_message_loss(self):
        """Test that event-driven approach doesn't lose messages."""
        session = Session()
        await session.start()
        
        try:
            # Execute code that produces multiple outputs
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
for i in range(10):
    print(f"Line {i}")
print("Final line")
""",
            )
            
            messages = []
            async for msg in session.execute(execute_msg):
                messages.append(msg)
            
            # Count output messages
            output_messages = [
                msg for msg in messages 
                if isinstance(msg, OutputMessage)
            ]
            
            # Should have received all outputs
            assert len(output_messages) >= 10, \
                f"Expected at least 10 output messages, got {len(output_messages)}"
            
            # Verify we got the final line
            final_found = any(
                "Final line" in msg.data 
                for msg in output_messages
            )
            assert final_found, "Should have received final output"
            
        finally:
            await session.terminate()
    
    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test basic execution works correctly."""
        session = Session()
        await session.start()
        
        try:
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code='print("Hello, World!")',
            )
            
            messages = []
            async for msg in session.execute(execute_msg):
                messages.append(msg)
            
            # Should get output and result
            output_found = any(
                isinstance(msg, OutputMessage) and "Hello, World!" in msg.data
                for msg in messages
            )
            assert output_found, "Should receive output"
            
            result_found = any(
                isinstance(msg, ResultMessage) for msg in messages
            )
            assert result_found, "Should receive result"
            
        finally:
            await session.terminate()


class TestMetricsCollection:
    """Test metrics collection."""
    
    @pytest.mark.asyncio
    async def test_metrics_tracking(self):
        """Test that metrics are properly tracked."""
        config = SessionConfig(enable_metrics=True)
        session = Session(config=config)
        await session.start()
        
        try:
            # Initial metrics should be zero
            assert session._metrics['cancel_event_triggers'] == 0
            assert session._metrics['executions_cancelled'] == 0
            
            # Execute some code
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code='import time; time.sleep(1); print("Done")',
            )
            
            messages = []
            async for msg in session.execute(execute_msg):
                messages.append(msg)
            
            # Normal execution shouldn't trigger cancellation
            assert session._metrics['cancel_event_triggers'] == 0
            assert session._metrics['executions_cancelled'] == 0
            
            # Now test cancellation
            execute_msg2 = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code='import time; time.sleep(30)',
            )
            
            task = asyncio.create_task(
                session.execute(execute_msg2).__anext__()
            )
            await asyncio.sleep(0.1)
            await session.terminate()
            
            # Should have triggered cancel event
            assert session._metrics['cancel_event_triggers'] > 0
            
        finally:
            await session.terminate()