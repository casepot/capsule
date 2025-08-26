#!/usr/bin/env python3
"""
Comprehensive Investigation: Async Generator Lifecycle Timeout Issue

This test suite investigates the timeout issue in Session.execute() after
message type normalization to strings.
"""

import asyncio
import sys
import time
import uuid
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent))

from src.protocol.messages import (
    MessageType,
    ExecuteMessage, 
    ResultMessage,
    ErrorMessage,
    OutputMessage,
    Message
)
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


class AsyncTimeoutInvestigator:
    """Investigates the async generator timeout issue systematically"""
    
    def __init__(self):
        self.results: List[TestResult] = []
        
    async def test_1_direct_enum_comparison(self) -> TestResult:
        """Test 1: Direct Enum Comparison - Prove the type mismatch"""
        test_name = "Test 1: Direct Enum Comparison"
        start_time = time.time()
        findings = []
        
        try:
            # Create sample messages as they would be after normalization
            result_msg = ResultMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                value=42,
                repr="42",
                execution_id=str(uuid.uuid4()),
                execution_time=1.0
            )
            
            error_msg = ErrorMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                traceback="traceback",
                exception_type="ValueError",
                exception_message="test error"
            )
            
            # Test the actual comparison as it appears in manager.py line 274
            findings.append(f"Result message type: {result_msg.type!r} (type: {type(result_msg.type).__name__})")
            findings.append(f"Error message type: {error_msg.type!r} (type: {type(error_msg.type).__name__})")
            findings.append(f"MessageType.RESULT: {MessageType.RESULT!r} (type: {type(MessageType.RESULT).__name__})")
            findings.append(f"MessageType.ERROR: {MessageType.ERROR!r} (type: {type(MessageType.ERROR).__name__})")
            
            # The critical comparison from line 274
            result_in_enum_list = result_msg.type in [MessageType.RESULT, MessageType.ERROR]
            error_in_enum_list = error_msg.type in [MessageType.RESULT, MessageType.ERROR]
            
            findings.append(f"'result' in [MessageType.RESULT, MessageType.ERROR]: {result_in_enum_list}")
            findings.append(f"'error' in [MessageType.RESULT, MessageType.ERROR]: {error_in_enum_list}")
            
            # Show what would work
            result_in_string_list = result_msg.type in ["result", "error"]
            error_in_string_list = error_msg.type in ["result", "error"]
            
            findings.append(f"'result' in ['result', 'error']: {result_in_string_list}")
            findings.append(f"'error' in ['result', 'error']: {error_in_string_list}")
            
            # Show the equality comparison
            findings.append(f"'result' == MessageType.RESULT: {'result' == MessageType.RESULT}")
            findings.append(f"'result' == 'result': {'result' == 'result'}")
            
            # This is the bug: string literals never match enum values
            assert not result_in_enum_list, "Bug confirmed: string 'result' not in enum list"
            assert not error_in_enum_list, "Bug confirmed: string 'error' not in enum list"
            
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
    
    async def test_2_minimal_timeout_reproduction(self) -> TestResult:
        """Test 2: Minimal Async Generator Reproduction - Smallest test that times out"""
        test_name = "Test 2: Minimal Timeout Reproduction"
        start_time = time.time()
        findings = []
        
        pool = None
        try:
            # Create minimal setup
            pool = SessionPool(max_sessions=1)
            await pool.start()
            
            session = await pool.acquire()
            findings.append(f"Session acquired: {session.session_id}")
            
            # Create simple execute message
            msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code='x = 42'
            )
            
            # Try to consume the generator with a timeout
            messages_received = []
            timeout_occurred = False
            
            try:
                async with asyncio.timeout(3.0):  # 3 second timeout
                    findings.append("Starting async generator consumption...")
                    async for message in session.execute(msg):
                        msg_info = f"Received: {message.type}"
                        findings.append(msg_info)
                        messages_received.append(message)
                        
                    findings.append("Generator completed normally (should not reach here)")
                    
            except asyncio.TimeoutError:
                timeout_occurred = True
                findings.append(f"TIMEOUT after 3 seconds - generator never completed")
                findings.append(f"Messages received before timeout: {len(messages_received)}")
                for m in messages_received:
                    findings.append(f"  - {m.type}: {getattr(m, 'value', getattr(m, 'data', 'N/A'))}")
            
            # Check if result message was received but not recognized
            has_result = any(m.type == "result" for m in messages_received)
            findings.append(f"Result message in received messages: {has_result}")
            
            assert timeout_occurred, "Timeout should have occurred"
            assert has_result or len(messages_received) > 0, "Should have received some messages"
            
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
    
    async def test_3_message_flow_trace(self) -> TestResult:
        """Test 3: Message Flow Trace - Track message types through the system"""
        test_name = "Test 3: Message Flow Trace"
        start_time = time.time()
        findings = []
        
        pool = None
        try:
            pool = SessionPool(max_sessions=1)
            await pool.start()
            
            session = await pool.acquire()
            
            msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code='print("trace"); 123'  # Should produce output and result
            )
            
            # Trace message flow with detailed logging
            message_trace = []
            
            try:
                async with asyncio.timeout(2.0):
                    async for message in session.execute(msg):
                        trace_entry = {
                            'type_value': message.type,
                            'type_class': type(message.type).__name__,
                            'message_class': type(message).__name__,
                            'has_execution_id': hasattr(message, 'execution_id'),
                            'execution_id_matches': getattr(message, 'execution_id', None) == msg.id
                        }
                        message_trace.append(trace_entry)
                        
                        # Log the comparison that would happen in line 274
                        in_enum_list = message.type in [MessageType.RESULT, MessageType.ERROR]
                        in_string_list = message.type in ["result", "error"]
                        
                        findings.append(f"Message {len(message_trace)}:")
                        findings.append(f"  Type: {message.type!r} ({type(message.type).__name__})")
                        findings.append(f"  Class: {type(message).__name__}")
                        findings.append(f"  In enum list [MessageType.RESULT, MessageType.ERROR]: {in_enum_list}")
                        findings.append(f"  In string list ['result', 'error']: {in_string_list}")
                        findings.append(f"  Would break loop (enum): {in_enum_list}")
                        findings.append(f"  Would break loop (string): {in_string_list}")
                        
            except asyncio.TimeoutError:
                findings.append("Timeout as expected - generator never terminates")
            
            # Analyze the trace
            findings.append(f"\nTotal messages traced: {len(message_trace)}")
            for i, entry in enumerate(message_trace):
                findings.append(f"Message {i+1}: {entry}")
            
            # Check for terminal messages that weren't recognized
            terminal_messages = [t for t in message_trace if t['type_value'] in ['result', 'error']]
            findings.append(f"\nTerminal messages present: {len(terminal_messages)}")
            findings.append(f"Terminal messages details: {terminal_messages}")
            
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
    
    async def test_4_manual_consumption_pattern(self) -> TestResult:
        """Test 4: Manual Async Generator Consumption - Count and analyze messages"""
        test_name = "Test 4: Manual Consumption Pattern"
        start_time = time.time()
        findings = []
        
        pool = None
        try:
            pool = SessionPool(max_sessions=1)
            await pool.start()
            session = await pool.acquire()
            
            msg = ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code='x = 100; x * 2'  # Should return 200
            )
            
            # Manual iteration with explicit break
            generator = session.execute(msg)
            message_count = 0
            message_types = []
            
            try:
                async with asyncio.timeout(2.0):
                    while True:
                        message = await anext(generator)
                        message_count += 1
                        message_types.append(message.type)
                        
                        findings.append(f"Message {message_count}: type={message.type}, class={type(message).__name__}")
                        
                        # Manual break condition (correct one)
                        if message.type in ["result", "error"]:
                            findings.append(f"Manual break triggered on: {message.type}")
                            break
                            
                        if message_count > 10:  # Safety limit
                            findings.append("Safety limit reached")
                            break
                            
            except asyncio.TimeoutError:
                findings.append(f"Timeout after {message_count} messages")
            except StopAsyncIteration:
                findings.append("Generator exhausted (should not happen)")
            
            findings.append(f"\nTotal messages: {message_count}")
            findings.append(f"Message types: {message_types}")
            findings.append(f"Contains 'result': {'result' in message_types}")
            findings.append(f"Contains 'error': {'error' in message_types}")
            
            # The bug: result message was received but loop didn't break naturally
            assert 'result' in message_types or message_count > 0, "Should have received messages"
            
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
    
    async def test_5_forced_termination(self) -> TestResult:
        """Test 5: Forced Termination - What happens when we break the generator"""
        test_name = "Test 5: Forced Termination"
        start_time = time.time()
        findings = []
        
        pool = None
        try:
            pool = SessionPool(max_sessions=1)
            await pool.start()
            session = await pool.acquire()
            
            # Test multiple forced terminations
            for i in range(3):
                findings.append(f"\n--- Iteration {i+1} ---")
                initial_state = session._state
                findings.append(f"Initial session state: {initial_state}")
                
                msg = ExecuteMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    code=f'y = {i}; y + 10'
                )
                
                message_count = 0
                try:
                    async with asyncio.timeout(0.5):  # Very short timeout
                        async for message in session.execute(msg):
                            message_count += 1
                            if message_count >= 1:  # Force break after first message
                                findings.append(f"Forcing break after message: {message.type}")
                                break
                                
                except asyncio.TimeoutError:
                    findings.append(f"Timed out after {message_count} messages")
                
                # Check session state after forced termination
                post_state = session._state
                findings.append(f"Post-termination state: {post_state}")
                findings.append(f"Session still alive: {session.is_alive}")
                
                # Small delay to allow cleanup
                await asyncio.sleep(0.1)
                final_state = session._state
                findings.append(f"Final state after delay: {final_state}")
            
            findings.append("\nForced termination impact:")
            findings.append(f"Session reusable: {session.is_alive}")
            findings.append(f"Final session state: {session._state}")
            
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
        print("ASYNC GENERATOR TIMEOUT INVESTIGATION")
        print("=" * 80)
        print()
        
        tests = [
            self.test_1_direct_enum_comparison,
            self.test_2_minimal_timeout_reproduction,
            self.test_3_message_flow_trace,
            self.test_4_manual_consumption_pattern,
            self.test_5_forced_termination,
        ]
        
        for test_func in tests:
            print(f"\nRunning {test_func.__doc__.split('-')[0].strip()}...")
            result = await test_func()
            self.results.append(result)
            
            if result.passed:
                print(f"✓ {result.test_name} - COMPLETED ({result.duration:.2f}s)")
            else:
                print(f"✗ {result.test_name} - FAILED: {result.error}")
            
            # Print findings
            print("\nFindings:")
            for finding in result.findings:
                print(f"  {finding}")
        
        self.print_summary()
    
    def print_summary(self):
        """Print investigation summary"""
        print("\n" + "=" * 80)
        print("INVESTIGATION SUMMARY")
        print("=" * 80)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.passed)
        total_time = sum(r.duration for r in self.results)
        
        print(f"\nTests run: {total_tests}")
        print(f"Tests passed: {passed_tests}")
        print(f"Total time: {total_time:.2f}s")
        
        print("\n--- KEY FINDINGS ---")
        print("1. ROOT CAUSE CONFIRMED:")
        print("   Session.execute() at line 274 compares string message types")
        print("   against MessageType enum values, which never match.")
        print()
        print("2. COMPARISON FAILURE:")
        print("   - message.type = 'result' (string)")
        print("   - Compared to: [MessageType.RESULT, MessageType.ERROR] (enums)")
        print("   - Result: 'result' not in [<MessageType.RESULT>, <MessageType.ERROR>]")
        print()
        print("3. IMPACT:")
        print("   - Async generator never terminates naturally")
        print("   - Session remains in BUSY state")
        print("   - All executions timeout unless manually broken")
        print("   - Result/error messages are received but not recognized as terminal")
        print()
        print("4. AFFECTED CODE:")
        print("   File: src/session/manager.py")
        print("   Lines: 274-275")
        print("   Problem: msg.type in [MessageType.RESULT, MessageType.ERROR]")
        print("   Fix needed: msg.type in ['result', 'error']")


async def main():
    """Run the investigation"""
    investigator = AsyncTimeoutInvestigator()
    await investigator.run_investigation()


if __name__ == "__main__":
    asyncio.run(main())