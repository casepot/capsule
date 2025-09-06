"""Tests for cooperative cancellation with hard cancel fallback."""

import asyncio
import pytest
import time
import uuid
from typing import AsyncIterator

from src.protocol.messages import (
    CancelMessage,
    ExecuteMessage,
    InterruptMessage,
    MessageType,
    OutputMessage,
    ErrorMessage,
    ResultMessage,
)
from src.session.manager import Session
from src.session.pool import SessionPool


class TestCooperativeCancellation:
    """Test cooperative cancellation via sys.settrace."""
    
    @pytest.mark.asyncio
    async def test_cancel_tight_loop(self):
        """Test cancellation of a tight Python loop."""
        session = Session()
        await session.start()
        
        try:
            # Start execution of infinite loop
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
print("STARTING EXECUTION")
import time
start = time.time()
counter = 0
# Infinite loop that will be cancelled
while True:
    counter += 1
    # Print progress less frequently to avoid overwhelming output
    if counter % 50000000 == 0:
        elapsed = time.time() - start
        print(f"Still running... counter={counter} at {elapsed:.2f}s")
    # Safety exit after 30 seconds (should never reach if cancel works)
    if time.time() - start > 30:
        print(f"Safety exit after {time.time() - start:.2f}s")
        break
print(f"FINISHED: Loop executed {counter} times in {time.time() - start:.2f}s")
""",
            )
            
            # Start execution in background
            execution_task = asyncio.create_task(
                self._collect_messages(session, execute_msg)
            )
            
            # Wait for execution to start and run a bit
            await asyncio.sleep(1.0)
            
            # Cancel the execution
            print(f"Cancelling execution {execute_msg.id}")
            cancelled = await session.cancel(execute_msg.id, grace_timeout_ms=500)
            print(f"Cancel returned: {cancelled}")
            assert cancelled, "Cancellation should succeed cooperatively"
            
            # Wait for execution to finish
            print("Waiting for execution task to complete...")
            messages = await execution_task
            print(f"Execution task completed with {len(messages)} messages")
            
            # Should have error about KeyboardInterrupt
            error_found = False
            print(f"\n=== Received {len(messages)} messages ===")
            for msg in messages:
                print(f"Message type: {msg.type}")
                if isinstance(msg, OutputMessage):
                    print(f"  Output: {msg.data[:100]}")
                elif isinstance(msg, ErrorMessage):
                    print(f"  Error: {msg.exception_type} - {msg.exception_message[:100]}")
                    if "KeyboardInterrupt" in msg.exception_type:
                        assert "cancelled" in msg.exception_message.lower()
                        error_found = True
                elif isinstance(msg, ResultMessage):
                    print(f"  Result value: {msg.value}, repr: {msg.repr[:100]}")
                    print(f"  Result execution_time: {msg.execution_time}")
            
            assert error_found, "Should receive KeyboardInterrupt error"
            
        finally:
            await session.shutdown()
    
    @pytest.mark.asyncio
    async def test_cancel_with_cleanup(self):
        """Test that finally blocks run during cancellation."""
        session = Session()
        await session.start()
        
        try:
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
cleanup_ran = False
try:
    while True:
        pass  # Infinite loop
finally:
    cleanup_ran = True
    print(f"Cleanup ran: {cleanup_ran}")
""",
            )
            
            # Start execution
            execution_task = asyncio.create_task(
                self._collect_messages(session, execute_msg)
            )
            
            # Wait for execution to start
            await asyncio.sleep(0.1)
            
            # Cancel execution
            await session.cancel(execute_msg.id, grace_timeout_ms=500)
            
            # Collect messages
            messages = await execution_task
            
            # Check that cleanup message was printed
            cleanup_found = False
            for msg in messages:
                if isinstance(msg, OutputMessage):
                    if "Cleanup ran: True" in msg.data:
                        cleanup_found = True
            
            assert cleanup_found, "Finally block should have executed"
            
        finally:
            await session.shutdown()
    
    @pytest.mark.asyncio
    async def test_cancel_during_computation(self):
        """Test cancellation during CPU-intensive computation."""
        session = Session()
        await session.start()
        
        try:
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

# Calculate large fibonacci numbers
results = []
for i in range(100):
    results.append(fibonacci(20))  # CPU intensive
    if i % 10 == 0:
        print(f"Calculated {i} fibonacci numbers")
        
print(f"Total results: {len(results)}")
""",
            )
            
            # Start execution
            execution_task = asyncio.create_task(
                self._collect_messages(session, execute_msg)
            )
            
            # Let it run for a bit
            await asyncio.sleep(0.2)
            
            # Cancel execution
            cancelled = await session.cancel(execute_msg.id, grace_timeout_ms=500)
            assert cancelled
            
            # Check messages
            messages = await execution_task
            
            # Should have some output but not complete
            output_count = sum(1 for msg in messages if isinstance(msg, OutputMessage))
            assert output_count > 0, "Should have some output"
            
            # Should not have completed all 100 iterations
            complete_found = False
            for msg in messages:
                if isinstance(msg, OutputMessage):
                    if "Total results: 100" in msg.data:
                        complete_found = True
            
            assert not complete_found, "Should not have completed all iterations"
            
        finally:
            await session.shutdown()
    
    async def _collect_messages(self, session: Session, execute_msg: ExecuteMessage) -> list:
        """Helper to collect all messages from an execution."""
        messages = []
        print(f"\nStarting to collect messages for execution {execute_msg.id}")
        async for msg in session.execute(execute_msg, timeout=10.0):
            print(f"Collected message: {msg.type}")
            messages.append(msg)
        print(f"Done collecting messages")
        return messages


class TestHardCancellation:
    """Test hard cancellation with worker restart."""
    # Deferred: hard blocking I/O cancellation semantics will be finished in Phase 3
    pytestmark = pytest.mark.xfail(
        reason="Deferred to Phase 3: blocking I/O cancellation semantics",
        strict=False,
    )
    
    @pytest.mark.asyncio
    async def test_cancel_blocking_io(self):
        """Test cancellation of blocking I/O operations."""
        session = Session()
        await session.start()
        
        try:
            # Execute blocking sleep
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
import time
print("Starting long sleep...")
time.sleep(30)  # Long blocking sleep
print("Sleep completed")
""",
            )
            
            # Start execution
            execution_task = asyncio.create_task(
                self._collect_messages_timeout(session, execute_msg, timeout=5.0)
            )
            
            # Wait for execution to start
            await asyncio.sleep(0.1)
            
            # Cancel with short grace period
            cancelled = await session.cancel(execute_msg.id, grace_timeout_ms=200)
            
            if not cancelled:
                # Worker should restart
                assert not session.is_alive, "Worker should be dead after hard cancel"
                await session.restart()
            
            # Execution should not complete
            messages = await execution_task
            
            # Should not see "Sleep completed"
            for msg in messages:
                if isinstance(msg, OutputMessage):
                    assert "Sleep completed" not in msg.data
            
        finally:
            await session.shutdown()
    
    @pytest.mark.asyncio
    async def test_interrupt_immediate(self):
        """Test immediate interrupt without grace period."""
        session = Session()
        await session.start()
        
        try:
            # Execute infinite loop
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
counter = 0
while True:
    counter += 1
    if counter % 1000000 == 0:
        print(f"Counter: {counter}")
""",
            )
            
            # Start execution
            execution_task = asyncio.create_task(
                self._collect_messages_timeout(session, execute_msg, timeout=5.0)
            )
            
            # Let it run briefly
            await asyncio.sleep(0.1)
            
            # Interrupt immediately
            await session.interrupt(execute_msg.id, force_restart=True)
            
            # Worker should restart
            if not session.is_alive:
                await session.restart()
            
            # Verify session is usable after restart
            test_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="print('Session works after interrupt')",
            )
            
            messages = []
            async for msg in session.execute(test_msg):
                messages.append(msg)
            
            # Should see the test output
            output_found = False
            for msg in messages:
                if isinstance(msg, OutputMessage):
                    if "Session works after interrupt" in msg.data:
                        output_found = True
            
            assert output_found, "Session should work after interrupt and restart"
            
        finally:
            await session.shutdown()
    
    async def _collect_messages_timeout(self, session: Session, execute_msg: ExecuteMessage, timeout: float) -> list:
        """Helper to collect messages with timeout handling."""
        messages = []
        try:
            async for msg in session.execute(execute_msg, timeout=timeout):
                messages.append(msg)
        except asyncio.TimeoutError:
            pass  # Expected for cancelled executions
        return messages


class TestCancellationWithInput:
    """Test cancellation during input() operations."""
    # Deferred: shutdown/cancellation behavior interacting with input() stabilizes in Phase 3
    pytestmark = pytest.mark.xfail(
        reason="Deferred to Phase 3: input EOF/timeout shutdown behavior",
        strict=False,
    )
    
    @pytest.mark.asyncio
    async def test_cancel_during_input(self):
        """Test cancellation while waiting for input."""
        session = Session()
        await session.start()
        
        try:
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
print("Waiting for input...")
try:
    name = input("Enter your name: ")
    print(f"Hello, {name}!")
except EOFError as e:
    print(f"Input cancelled: {e}")
except KeyboardInterrupt as e:
    print(f"Execution cancelled: {e}")
""",
            )
            
            # Start execution
            messages = []
            execution_task = asyncio.create_task(
                self._collect_with_input(session, execute_msg, messages)
            )
            
            # Wait for input prompt
            await asyncio.sleep(0.2)
            
            # Cancel while waiting for input
            await session.cancel(execute_msg.id, grace_timeout_ms=500)
            
            # Wait for execution to complete
            await execution_task
            
            # Should see cancellation message
            cancel_found = False
            for msg in messages:
                if isinstance(msg, OutputMessage):
                    if "cancelled" in msg.data.lower():
                        cancel_found = True
            
            assert cancel_found, "Should see cancellation message"
            
        finally:
            await session.shutdown()
    
    async def _collect_with_input(self, session: Session, execute_msg: ExecuteMessage, messages: list):
        """Helper to collect messages including input handling."""
        try:
            async for msg in session.execute(execute_msg, timeout=5.0):
                messages.append(msg)
        except asyncio.TimeoutError:
            pass


class TestPoolCancellation:
    """Test cancellation with session pool."""
    
    @pytest.mark.asyncio
    async def test_pool_recovery_after_hard_cancel(self):
        """Test that pool recovers after hard cancellation."""
        pool = SessionPool(min_idle=2, max_sessions=5)
        await pool.start()
        
        try:
            # Acquire session
            session = await pool.acquire()
            
            # Execute blocking code
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="import time; time.sleep(100)",
            )
            
            # Start execution
            execution_task = asyncio.create_task(
                self._run_with_timeout(session, execute_msg)
            )
            
            # Cancel with short grace period (forcing hard cancel)
            await asyncio.sleep(0.1)
            cancelled = await session.cancel(execute_msg.id, grace_timeout_ms=100)
            
            # Release session (should handle restart if needed)
            await pool.release(session, restart_if_dead=True)
            
            # Pool metrics should show restart
            metrics = pool.get_metrics()
            if not cancelled:
                assert metrics.sessions_restarted > 0, "Should have restarted session"
            
            # Acquire another session and verify it works
            session2 = await pool.acquire()
            
            test_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="print('Pool recovery test')",
            )
            
            messages = []
            async for msg in session2.execute(test_msg):
                messages.append(msg)
            
            # Should execute successfully
            output_found = False
            for msg in messages:
                if isinstance(msg, OutputMessage):
                    if "Pool recovery test" in msg.data:
                        output_found = True
            
            assert output_found, "Pool should provide working sessions after hard cancel"
            
            await pool.release(session2)
            
        finally:
            await pool.stop()
    
    async def _run_with_timeout(self, session: Session, execute_msg: ExecuteMessage):
        """Helper to run execution with timeout."""
        try:
            async for _ in session.execute(execute_msg, timeout=5.0):
                pass
        except asyncio.TimeoutError:
            pass


class TestCancellationPerformance:
    """Test performance impact of cancellation."""
    # Deferred to Phase 3: fine-tuning cancellation performance targets
    pytestmark = pytest.mark.xfail(
        reason="Deferred to Phase 3: cancellation performance",
        strict=False,
    )

    @pytest.mark.asyncio
    async def test_trace_overhead(self):
        """Test that trace function has minimal overhead."""
        session = Session()
        await session.start()
        
        try:
            # Run computation without cancellation
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
import time
start = time.time()
total = 0
for i in range(1000000):
    total += i
elapsed = time.time() - start
print(f"Time: {elapsed:.3f}s, Result: {total}")
""",
            )
            
            start_time = time.time()
            messages = []
            async for msg in session.execute(execute_msg):
                messages.append(msg)
            execution_time = time.time() - start_time
            
            # Extract reported time from output
            reported_time = None
            for msg in messages:
                if isinstance(msg, OutputMessage):
                    if "Time:" in msg.data:
                        parts = msg.data.split("Time:")[1].split("s")[0]
                        reported_time = float(parts.strip())
            
            assert reported_time is not None, "Should report execution time"
            
            # Overhead should be minimal (less than 50%)
            overhead_ratio = execution_time / reported_time
            assert overhead_ratio < 1.5, f"Trace overhead too high: {overhead_ratio:.2f}x"
            
        finally:
            await session.shutdown()
    
    @pytest.mark.asyncio
    async def test_cancel_responsiveness(self):
        """Test how quickly cancellation takes effect."""
        session = Session()
        await session.start()
        
        try:
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
import time
start = time.time()
while True:
    if time.time() - start > 10:
        break
""",
            )
            
            # Start execution
            execution_task = asyncio.create_task(
                self._run_until_cancel(session, execute_msg)
            )
            
            # Measure cancellation time
            await asyncio.sleep(0.1)  # Let it start
            
            cancel_start = time.time()
            await session.cancel(execute_msg.id, grace_timeout_ms=500)
            cancel_time = time.time() - cancel_start
            
            await execution_task
            
            # Cancellation should be responsive (under 100ms for tight loop)
            assert cancel_time < 0.1, f"Cancellation took too long: {cancel_time:.3f}s"
            
        finally:
            await session.shutdown()
    
    async def _run_until_cancel(self, session: Session, execute_msg: ExecuteMessage):
        """Helper to run until cancelled."""
        try:
            async for _ in session.execute(execute_msg, timeout=5.0):
                pass
        except asyncio.TimeoutError:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
