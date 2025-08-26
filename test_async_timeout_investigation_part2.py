#!/usr/bin/env python3
"""
Part 2: Deep Investigation of Integration Test Timeout

Since the enum comparison actually works (MessageType inherits from str),
we need to investigate why the integration test still times out.
"""

import asyncio
import sys
import time
import uuid
from pathlib import Path
from typing import List, Optional, Any
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent))

from src.protocol.messages import ExecuteMessage, Message
from src.session.pool import SessionPool
from src.session.manager import Session


@dataclass
class TestResult:
    """Container for test results"""
    test_name: str
    passed: bool
    duration: float
    findings: List[str]
    error: Optional[str] = None


class IntegrationTimeoutInvestigator:
    """Investigates the actual integration test timeout issue"""
    
    async def test_6_multiple_executions(self) -> TestResult:
        """Test 6: Multiple Execution Pattern - Sequential executions"""
        test_name = "Test 6: Multiple Executions"
        start_time = time.time()
        findings = []
        
        pool = None
        try:
            pool = SessionPool(max_sessions=1)
            await pool.start()
            session = await pool.acquire()
            
            # Try multiple executions in sequence
            for i in range(3):
                findings.append(f"\n--- Execution {i+1} ---")
                
                msg = ExecuteMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    code=f'x = {i}; x * 10'
                )
                
                messages = []
                try:
                    async with asyncio.timeout(2.0):
                        async for message in session.execute(msg):
                            messages.append(message.type)
                        findings.append(f"Execution {i+1} completed normally")
                        findings.append(f"Messages: {messages}")
                except asyncio.TimeoutError:
                    findings.append(f"Execution {i+1} timed out!")
                    findings.append(f"Messages before timeout: {messages}")
                    break
                
            findings.append(f"\nCompleted {i+1} executions")
            findings.append(f"Session state: {session._state}")
            
            return TestResult(
                test_name=test_name,
                passed=True,
                duration=time.time() - start_time,
                findings=findings
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                duration=time.time() - start_time,
                findings=findings,
                error=str(e)
            )
        finally:
            if pool:
                await pool.stop()
    
    async def test_7_error_handling(self) -> TestResult:
        """Test 7: Error Message Handling - Execute code that produces errors"""
        test_name = "Test 7: Error Handling"
        start_time = time.time()
        findings = []
        
        pool = None
        try:
            pool = SessionPool(max_sessions=1)
            await pool.start()
            session = await pool.acquire()
            
            # Test error-producing code
            error_codes = [
                ("1/0", "ZeroDivisionError"),
                ("undefined_var", "NameError"),
                ("int('not a number')", "ValueError")
            ]
            
            for code, expected_error in error_codes:
                findings.append(f"\n--- Testing: {code} ---")
                
                msg = ExecuteMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    code=code
                )
                
                messages = []
                error_found = False
                
                try:
                    async with asyncio.timeout(2.0):
                        async for message in session.execute(msg):
                            messages.append(message.type)
                            if message.type == "error":
                                error_found = True
                                findings.append(f"Error message received: {getattr(message, 'exception_type', 'N/A')}")
                        
                        findings.append(f"Generator completed with messages: {messages}")
                        
                except asyncio.TimeoutError:
                    findings.append(f"Timed out! Messages: {messages}")
                
                findings.append(f"Error found: {error_found}")
                findings.append(f"Expected error: {expected_error}")
            
            return TestResult(
                test_name=test_name,
                passed=True,
                duration=time.time() - start_time,
                findings=findings
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                duration=time.time() - start_time,
                findings=findings,
                error=str(e)
            )
        finally:
            if pool:
                await pool.stop()
    
    async def test_8_queue_behavior(self) -> TestResult:
        """Test 8: Queue Behavior Analysis - Examine message queue during execution"""
        test_name = "Test 8: Queue Behavior"
        start_time = time.time()
        findings = []
        
        pool = None
        try:
            pool = SessionPool(max_sessions=1)
            await pool.start()
            session = await pool.acquire()
            
            # Create execution
            msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code='import time; time.sleep(0.1); "done"'
            )
            
            # Start execution in background
            execution_task = asyncio.create_task(self._consume_with_timeout(session, msg))
            
            # Check queue state while executing
            await asyncio.sleep(0.05)  # Let execution start
            
            queue_key = f"execution:{msg.id}"
            if queue_key in session._message_handlers:
                queue = session._message_handlers[queue_key]
                findings.append(f"Queue exists: True")
                findings.append(f"Queue size: {queue.qsize()}")
            else:
                findings.append(f"Queue exists: False (not created yet)")
            
            # Wait for execution to complete
            messages = await execution_task
            findings.append(f"\nExecution completed with {len(messages)} messages")
            findings.append(f"Message types: {[m.type for m in messages]}")
            
            # Check queue cleanup
            if queue_key in session._message_handlers:
                findings.append(f"Queue still exists after completion: True")
            else:
                findings.append(f"Queue cleaned up: True")
            
            return TestResult(
                test_name=test_name,
                passed=True,
                duration=time.time() - start_time,
                findings=findings
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                duration=time.time() - start_time,
                findings=findings,
                error=str(e)
            )
        finally:
            if pool:
                await pool.stop()
    
    async def _consume_with_timeout(self, session: Session, msg: ExecuteMessage) -> List[Message]:
        """Helper to consume generator with timeout"""
        messages = []
        try:
            async with asyncio.timeout(3.0):
                async for message in session.execute(msg):
                    messages.append(message)
        except asyncio.TimeoutError:
            pass
        return messages
    
    async def test_9_state_transitions(self) -> TestResult:
        """Test 9: State Machine Analysis - Track session state transitions"""
        test_name = "Test 9: State Transitions"
        start_time = time.time()
        findings = []
        
        pool = None
        try:
            pool = SessionPool(max_sessions=1)
            await pool.start()
            session = await pool.acquire()
            
            initial_state = session._state
            findings.append(f"Initial state: {initial_state}")
            
            msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code='42'
            )
            
            state_log = []
            
            # Track states during execution
            async def track_states():
                for _ in range(10):
                    state_log.append((time.time(), session._state))
                    await asyncio.sleep(0.05)
            
            # Start state tracking
            track_task = asyncio.create_task(track_states())
            
            # Execute
            messages = []
            async for message in session.execute(msg):
                messages.append(message)
                state_log.append((time.time(), f"Received {message.type}", session._state))
            
            await track_task
            
            findings.append(f"\nState transitions:")
            start = state_log[0][0] if state_log else time.time()
            for entry in state_log:
                if len(entry) == 2:
                    t, state = entry
                    findings.append(f"  +{(t-start)*1000:.1f}ms: {state}")
                else:
                    t, event, state = entry
                    findings.append(f"  +{(t-start)*1000:.1f}ms: {event} -> {state}")
            
            final_state = session._state
            findings.append(f"\nFinal state: {final_state}")
            findings.append(f"Messages received: {[m.type for m in messages]}")
            
            return TestResult(
                test_name=test_name,
                passed=True,
                duration=time.time() - start_time,
                findings=findings
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                duration=time.time() - start_time,
                findings=findings,
                error=str(e)
            )
        finally:
            if pool:
                await pool.stop()
    
    async def test_10_concurrent_impact(self) -> TestResult:
        """Test 10: Concurrent Execution Impact - Multiple sessions"""
        test_name = "Test 10: Concurrent Impact"
        start_time = time.time()
        findings = []
        
        pool = None
        try:
            pool = SessionPool(max_sessions=3)
            await pool.start()
            
            # Get multiple sessions
            sessions = []
            for i in range(3):
                session = await pool.acquire()
                sessions.append(session)
                findings.append(f"Acquired session {i+1}: {session.session_id}")
            
            # Execute concurrently
            async def execute_on_session(session: Session, index: int):
                msg = ExecuteMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    code=f'result = {index * 100}'
                )
                
                messages = []
                try:
                    async with asyncio.timeout(2.0):
                        async for message in session.execute(msg):
                            messages.append(message.type)
                    return f"Session {index} completed: {messages}"
                except asyncio.TimeoutError:
                    return f"Session {index} timed out after: {messages}"
            
            # Run all concurrently
            tasks = [execute_on_session(s, i) for i, s in enumerate(sessions)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            findings.append("\nConcurrent execution results:")
            for result in results:
                findings.append(f"  {result}")
            
            # Check pool state
            findings.append(f"\nPool state after concurrent execution:")
            findings.append(f"  Active sessions: {len(pool._sessions)}")
            findings.append(f"  Idle sessions: {len(pool._idle_sessions)}")
            
            # Try to release sessions
            for session in sessions:
                await pool.release(session)
            
            findings.append(f"\nAfter release:")
            findings.append(f"  Active sessions: {len(pool._sessions)}")
            findings.append(f"  Idle sessions: {len(pool._idle_sessions)}")
            
            return TestResult(
                test_name=test_name,
                passed=True,
                duration=time.time() - start_time,
                findings=findings
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                duration=time.time() - start_time,
                findings=findings,
                error=str(e)
            )
        finally:
            if pool:
                await pool.stop()
    
    async def test_integration_timeout_reproduction(self) -> TestResult:
        """Special Test: Reproduce the exact integration test timeout"""
        test_name = "Integration Test Reproduction"
        start_time = time.time()
        findings = []
        
        pool = None
        try:
            # Reproduce the exact pattern from test_integration_message_types.py
            pool = SessionPool(max_sessions=1)
            await pool.start()
            
            session = await pool.acquire()
            findings.append(f"Session acquired: {session.session_id}")
            
            # This is the exact pattern that times out
            class ExecutionResult:
                def __init__(self):
                    self.output = ""
                    self.error = None
                    self.messages = []
                
                async def collect(self, session: Session, code: str):
                    msg = ExecuteMessage(
                        id=str(uuid.uuid4()),
                        timestamp=time.time(),
                        code=code
                    )
                    
                    async for message in session.execute(msg):
                        self.messages.append(message)
                        if message.type == "output":
                            self.output += message.data
                        elif message.type == "error":
                            self.error = message.exception_message
            
            # Try the exact code from the integration test
            result = ExecutionResult()
            
            findings.append("Starting execution with pattern from integration test...")
            try:
                async with asyncio.timeout(5.0):
                    await result.collect(session, "x = 42; print(f'Value: {x}')")
                    findings.append(f"Execution completed normally!")
                    findings.append(f"Output: {result.output!r}")
                    findings.append(f"Messages: {[m.type for m in result.messages]}")
            except asyncio.TimeoutError:
                findings.append(f"TIMEOUT occurred!")
                findings.append(f"Messages before timeout: {[m.type for m in result.messages]}")
                findings.append(f"Output collected: {result.output!r}")
            
            findings.append(f"\nSession state after: {session._state}")
            
            return TestResult(
                test_name=test_name,
                passed=True,
                duration=time.time() - start_time,
                findings=findings
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                duration=time.time() - start_time,
                findings=findings,
                error=str(e)
            )
        finally:
            if pool:
                await pool.stop()
    
    async def run_investigation(self):
        """Run all investigation tests"""
        print("=" * 80)
        print("INTEGRATION TIMEOUT INVESTIGATION - PART 2")
        print("=" * 80)
        print()
        
        tests = [
            self.test_6_multiple_executions,
            self.test_7_error_handling,
            self.test_8_queue_behavior,
            self.test_9_state_transitions,
            self.test_10_concurrent_impact,
            self.test_integration_timeout_reproduction,
        ]
        
        for test_func in tests:
            print(f"\nRunning {test_func.__doc__.split('-')[0].strip()}...")
            result = await test_func()
            
            if result.passed:
                print(f"✓ {result.test_name} - COMPLETED ({result.duration:.2f}s)")
            else:
                print(f"✗ {result.test_name} - FAILED: {result.error}")
            
            # Print findings
            print("\nFindings:")
            for finding in result.findings:
                print(f"  {finding}")
        
        print("\n" + "=" * 80)
        print("INVESTIGATION COMPLETE")
        print("=" * 80)


async def main():
    """Run the investigation"""
    investigator = IntegrationTimeoutInvestigator()
    await investigator.run_investigation()


if __name__ == "__main__":
    asyncio.run(main())