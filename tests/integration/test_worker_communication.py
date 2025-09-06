"""Integration tests for worker subprocess communication.

Tests the complete communication pipeline between Session and Worker processes,
including protocol framing, message serialization, and transport layer.
"""

import pytest
import asyncio
import time
import uuid
from typing import List, AsyncIterator
from src.session.manager import Session, SessionState
from src.protocol.messages import (
    MessageType,
    ExecuteMessage,
    OutputMessage,
    ResultMessage,
    ErrorMessage,
    HeartbeatMessage,
    InputMessage,
    InputResponseMessage,
    CheckpointMessage,
    RestoreMessage,
    ReadyMessage,
)


@pytest.mark.integration
class TestWorkerProtocol:
    """Test worker subprocess protocol communication."""
    
    @pytest.mark.asyncio
    async def test_basic_message_exchange(self):
        """Test basic message exchange between session and worker."""
        session = Session()
        await session.start()
        
        try:
            # Send execute message  
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="42"  # Simple expression first
            )
            
            messages = []
            async for msg in session.execute(execute_msg):
                messages.append(msg)
            
            # Should receive result only for simple expression
            assert len(messages) == 1
            
            # Check result 
            results = [m for m in messages if isinstance(m, ResultMessage)]
            assert len(results) == 1
            # Debug print the result
            print(f"Result value: {results[0].value!r}, type: {type(results[0].value)}")
            assert results[0].value == 42
            
        finally:
            await session.shutdown()
    
    @pytest.mark.skip(reason="Heartbeats are handled internally, not exposed via execute()")
    @pytest.mark.asyncio
    async def test_heartbeat_mechanism(self):
        """Test heartbeat messages from worker."""
        session = Session()
        await session.start()
        
        try:
            # Start long-running execution
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
import time
for i in range(3):
    time.sleep(0.5)
    print(f"Iteration {i}")
"completed"
"""
            )
            
            messages = []
            heartbeats = []
            
            async for msg in session.execute(execute_msg, timeout=5.0):
                messages.append(msg)
                if isinstance(msg, HeartbeatMessage):
                    heartbeats.append(msg)
            
            # Should receive heartbeats during execution
            assert len(heartbeats) > 0, "Should receive heartbeat messages"
            
            # Should complete successfully
            assert any(isinstance(m, ResultMessage) and m.value == "completed" 
                      for m in messages)
            
        finally:
            await session.shutdown()
    
    @pytest.mark.asyncio
    async def test_error_propagation(self):
        """Test error message propagation from worker."""
        session = Session()
        await session.start()
        
        try:
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="raise ValueError('Test error from worker')"
            )
            
            messages = []
            async for msg in session.execute(execute_msg):
                messages.append(msg)
            
            # Should receive error message
            errors = [m for m in messages if isinstance(m, ErrorMessage)]
            assert len(errors) == 1
            assert errors[0].exception_type == "ValueError"
            assert "Test error from worker" in errors[0].exception_message
            assert errors[0].traceback is not None
            
        finally:
            await session.shutdown()
    
    @pytest.mark.asyncio
    async def test_concurrent_message_handling(self):
        """Test handling multiple messages in quick succession."""
        session = Session()
        await session.start()
        
        try:
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
# Generate multiple output messages rapidly
for i in range(10):
    print(f"Message {i}")
"all_done"
"""
            )
            
            messages = []
            output_count = 0
            
            async for msg in session.execute(execute_msg):
                messages.append(msg)
                if isinstance(msg, OutputMessage):
                    output_count += 1
            
            # Should receive all output messages
            assert output_count == 10, f"Should receive 10 output messages, got {output_count}"
            
            # Should receive final result
            assert any(isinstance(m, ResultMessage) and m.value == "all_done" 
                      for m in messages)
            
        finally:
            await session.shutdown()


@pytest.mark.integration
class TestCheckpointProtocol:
    """Test checkpoint/restore protocol communication."""
    
    @pytest.mark.asyncio
    async def test_checkpoint_create_and_restore(self):
        """Test checkpoint creation and restoration via protocol."""
        session = Session()
        await session.start()
        
        try:
            # Set up initial state
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
x = 100
y = [1, 2, 3]
def compute(n):
    return n * x
"state_initialized"
"""
            )
            
            messages = []
            async for msg in session.execute(execute_msg):
                messages.append(msg)
            
            # Create checkpoint
            checkpoint_msg = CheckpointMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                checkpoint_id="test_checkpoint_1"
            )
            
            # Send checkpoint message directly via transport, then observe via interceptor
            checkpoint_ready = asyncio.Event()

            def on_ready_checkpoint(msg):
                # Treat either an explicit CheckpointMessage or a ReadyMessage as confirmation
                if (isinstance(msg, ReadyMessage) or isinstance(msg, CheckpointMessage)) and not checkpoint_ready.is_set():
                    checkpoint_ready.set()
                return None

            session.add_message_interceptor(on_ready_checkpoint)

            await session._transport.send_message(checkpoint_msg)

            # Wait for checkpoint confirmation without reading the transport directly
            await asyncio.wait_for(checkpoint_ready.wait(), timeout=2.0)
            session.remove_message_interceptor(on_ready_checkpoint)
            
            # Modify state
            execute_msg2 = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="x = 999; y = ['modified']"
            )
            
            async for msg in session.execute(execute_msg2):
                pass
            
            # Restore checkpoint
            restore_msg = RestoreMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                checkpoint_id="test_checkpoint_1"
            )
            
            restore_ready = asyncio.Event()

            def on_ready_restore(msg):
                if isinstance(msg, ReadyMessage) and not restore_ready.is_set():
                    restore_ready.set()
                return None

            session.add_message_interceptor(on_ready_restore)

            await session._transport.send_message(restore_msg)

            # Wait for restore confirmation via interceptor
            await asyncio.wait_for(restore_ready.wait(), timeout=2.0)
            session.remove_message_interceptor(on_ready_restore)
            
            # Verify state was restored
            verify_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="(x, y)"
            )
            
            messages = []
            async for msg in session.execute(verify_msg):
                messages.append(msg)
            
            results = [m for m in messages if isinstance(m, ResultMessage)]
            assert len(results) == 1
            # Allow msgpack to normalize tuples to lists
            assert results[0].value == (100, [1, 2, 3]) or results[0].value == [100, [1, 2, 3]]
            
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_restore_merge_only_preserves_extras_when_clear_false(self):
        session = Session()
        await session.start()
        try:
            # Initialize some state and checkpoint
            exec_init = ExecuteMessage(id=str(uuid.uuid4()), timestamp=time.time(), code="a=1; b=2; 'ok'")
            async for _ in session.execute(exec_init):
                pass

            cp_msg = CheckpointMessage(id=str(uuid.uuid4()), timestamp=time.time(), checkpoint_id="cp_merge")
            ready_ev = asyncio.Event()
            def on_ready(msg):
                if isinstance(msg, ReadyMessage) and not ready_ev.is_set():
                    ready_ev.set()
                return None
            session.add_message_interceptor(on_ready)
            await session._transport.send_message(cp_msg)
            await asyncio.wait_for(ready_ev.wait(), timeout=2.0)
            session.remove_message_interceptor(on_ready)

            # Add extra live state not in checkpoint
            exec_mut = ExecuteMessage(id=str(uuid.uuid4()), timestamp=time.time(), code="c=3; 'mut'")
            async for _ in session.execute(exec_mut):
                pass

            # Restore with clear_existing=False (merge-only)
            rs_msg = RestoreMessage(id=str(uuid.uuid4()), timestamp=time.time(), checkpoint_id="cp_merge", clear_existing=False)
            ready2 = asyncio.Event()
            def on_ready2(msg):
                if isinstance(msg, ReadyMessage) and not ready2.is_set():
                    ready2.set()
                return None
            session.add_message_interceptor(on_ready2)
            await session._transport.send_message(rs_msg)
            await asyncio.wait_for(ready2.wait(), timeout=2.0)
            session.remove_message_interceptor(on_ready2)

            # Verify extras preserved and checkpointed values restored
            verify = ExecuteMessage(id=str(uuid.uuid4()), timestamp=time.time(), code="(a,b,c)")
            msgs = [m async for m in session.execute(verify)]
            res = [m for m in msgs if isinstance(m, ResultMessage)][0]
            val = res.value if not isinstance(res.value, list) else tuple(res.value)
            assert val == (1,2,3)
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_restore_clear_existing_replaces_extras(self):
        session = Session()
        await session.start()
        try:
            # Initialize state and checkpoint
            m1 = ExecuteMessage(id=str(uuid.uuid4()), timestamp=time.time(), code="x=10; y=20; 'ok'")
            async for _ in session.execute(m1):
                pass
            cp = CheckpointMessage(id=str(uuid.uuid4()), timestamp=time.time(), checkpoint_id="cp_clear")
            rd = asyncio.Event()
            def on_ready(msg):
                if isinstance(msg, ReadyMessage) and not rd.is_set():
                    rd.set()
                return None
            session.add_message_interceptor(on_ready)
            await session._transport.send_message(cp)
            await asyncio.wait_for(rd.wait(), timeout=2.0)
            session.remove_message_interceptor(on_ready)

            # Add extra state and mutate checkpointed state
            m2 = ExecuteMessage(id=str(uuid.uuid4()), timestamp=time.time(), code="x=999; z='extra'; 'mut' ")
            async for _ in session.execute(m2):
                pass

            # Restore with clear_existing=True
            rs = RestoreMessage(id=str(uuid.uuid4()), timestamp=time.time(), checkpoint_id="cp_clear", clear_existing=True)
            rd2 = asyncio.Event()
            def on_ready2(msg):
                if isinstance(msg, ReadyMessage) and not rd2.is_set():
                    rd2.set()
                return None
            session.add_message_interceptor(on_ready2)
            await session._transport.send_message(rs)
            await asyncio.wait_for(rd2.wait(), timeout=2.0)
            session.remove_message_interceptor(on_ready2)

            # Verify extras removed, checkpointed values restored
            v = ExecuteMessage(id=str(uuid.uuid4()), timestamp=time.time(), code="('x' in globals(), 'y' in globals(), 'z' in globals(), x, y)")
            msgs = [m async for m in session.execute(v)]
            res = [m for m in msgs if isinstance(m, ResultMessage)][0]
            okx, oky, okz, xv, yv = res.value if not isinstance(res.value, list) else tuple(res.value)
            assert okx and oky and not okz
            assert xv == 10 and yv == 20
        finally:
            await session.shutdown()


@pytest.mark.integration
class TestInputProtocol:
    """Test input request/response protocol."""
    
    @pytest.mark.asyncio
    async def test_input_request_response(self):
        """Test input() handling via protocol messages."""
        session = Session()
        await session.start()
        
        try:
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
name = input("Enter name: ")
print(f"Hello {name}!")
"""
            )
            
            # Execute and handle input
            messages = []
            input_count = 0
            
            async for msg in session.execute(execute_msg):
                messages.append(msg)
                
                if isinstance(msg, InputMessage):
                    # Respond to input request
                    await session.input_response(msg.id, "Test User")
                    input_count += 1
            
            # Verify we got an input request
            assert input_count == 1
            
            # Verify output
            outputs = [m for m in messages if isinstance(m, OutputMessage)]
            assert any("Hello Test User!" in o.data for o in outputs)
            
            # Verify we got a result message (value might be None due to serialization)
            results = [m for m in messages if isinstance(m, ResultMessage)]
            assert len(results) == 1
            
        finally:
            await session.shutdown()
    


@pytest.mark.integration
class TestTransportReliability:
    """Test transport layer reliability and error handling."""
    
    @pytest.mark.asyncio
    async def test_large_message_handling(self):
        """Test handling of large messages through transport."""
        session = Session()
        await session.start()
        
        try:
            # Generate large output
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
# Generate large string
large_data = 'x' * 100000
print(f"Data length: {len(large_data)}")
len(large_data)
"""
            )
            
            messages = []
            async for msg in session.execute(execute_msg):
                messages.append(msg)
            
            # Should handle large data successfully
            results = [m for m in messages if isinstance(m, ResultMessage)]
            assert len(results) == 1
            assert results[0].value == 100000
            
        finally:
            await session.shutdown()
    
    @pytest.mark.asyncio
    async def test_message_ordering(self):
        """Test that messages maintain order through transport."""
        session = Session()
        await session.start()
        
        try:
            execute_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="""
for i in range(5):
    print(f"Output {i}")
"completed"
"""
            )
            
            messages = []
            async for msg in session.execute(execute_msg):
                messages.append(msg)
            
            # Extract output messages
            outputs = [m for m in messages if isinstance(m, OutputMessage)]
            
            # Verify ordering
            for i, output in enumerate(outputs):
                assert f"Output {i}" in output.data
            
        finally:
            await session.shutdown()
    
    @pytest.mark.asyncio
    async def test_transport_recovery_after_error(self):
        """Test that transport recovers after handling error messages."""
        session = Session()
        await session.start()
        
        try:
            # First execution with error
            error_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="1/0"
            )
            
            error_messages = []
            async for msg in session.execute(error_msg):
                error_messages.append(msg)
            
            assert any(isinstance(m, ErrorMessage) for m in error_messages)
            
            # Second execution should work normally
            success_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="2 + 2"
            )
            
            success_messages = []
            async for msg in session.execute(success_msg):
                success_messages.append(msg)
            
            results = [m for m in success_messages if isinstance(m, ResultMessage)]
            assert len(results) == 1
            assert results[0].value == 4
            
        finally:
            await session.shutdown()


@pytest.mark.integration
class TestWorkerLifecycle:
    """Test worker subprocess lifecycle management."""
    
    @pytest.mark.asyncio
    async def test_worker_startup_shutdown(self):
        """Test clean worker startup and shutdown."""
        session = Session()
        
        # Verify initial state
        assert session.state == SessionState.CREATING
        assert not session.is_alive
        
        # Start worker
        await session.start()
        assert session.state == SessionState.READY
        assert session.is_alive
        
        # Execute something to verify it's working
        execute_msg = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code="'worker_active'"
        )
        
        messages = []
        async for msg in session.execute(execute_msg):
            messages.append(msg)
        
        assert any(isinstance(m, ResultMessage) and m.value == "worker_active" 
                  for m in messages)
        
        # Shutdown
        await session.shutdown()
        assert session.state == SessionState.TERMINATED
        assert not session.is_alive
    
    @pytest.mark.asyncio
    async def test_worker_restart_after_crash(self):
        """Test worker restart after crash."""
        session = Session()
        await session.start()
        
        try:
            # Crash the worker
            crash_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="import os; os._exit(1)"
            )
            
            messages = []
            try:
                async for msg in session.execute(crash_msg, timeout=2.0):
                    messages.append(msg)
            except Exception:
                pass  # Expected due to crash
            
            # Worker should be dead
            assert not session.is_alive
            
            # Restart worker
            await session.restart()
            assert session.is_alive
            assert session.state == SessionState.READY
            
            # Verify restarted worker is functional
            test_msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code="'restarted_successfully'"
            )
            
            messages = []
            async for msg in session.execute(test_msg):
                messages.append(msg)
            
            assert any(isinstance(m, ResultMessage) and m.value == "restarted_successfully"
                      for m in messages)
            
        finally:
            await session.shutdown()
    
    @pytest.mark.asyncio
    async def test_multiple_worker_sessions(self):
        """Test multiple worker sessions running concurrently."""
        sessions = []
        
        try:
            # Start multiple sessions
            for i in range(3):
                session = Session()
                await session.start()
                sessions.append(session)
            
            # Execute on each session
            tasks = []
            for i, session in enumerate(sessions):
                execute_msg = ExecuteMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    code=f"'session_{i}'"
                )
                
                async def execute_and_collect(sess, msg, expected):
                    messages = []
                    async for m in sess.execute(msg):
                        messages.append(m)
                    results = [m for m in messages if isinstance(m, ResultMessage)]
                    assert len(results) == 1
                    assert results[0].value == expected
                    return True
                
                task = asyncio.create_task(
                    execute_and_collect(session, execute_msg, f"session_{i}")
                )
                tasks.append(task)
            
            # Wait for all to complete
            results = await asyncio.gather(*tasks)
            assert all(results)
            
        finally:
            # Cleanup all sessions
            for session in sessions:
                await session.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
