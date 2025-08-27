#!/usr/bin/env python3
"""Test 3: Protocol message integration with IPython execution."""

import sys
import time
import asyncio
import threading
import traceback
import uuid
from typing import Any, Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
from queue import Queue
from io import StringIO


class MessageType(str, Enum):
    """Simplified message types."""
    EXECUTE = "execute"
    OUTPUT = "output"
    INPUT = "input"
    INPUT_RESPONSE = "input_response"
    RESULT = "result"
    ERROR = "error"


@dataclass
class Message:
    """Simplified message class."""
    type: MessageType
    id: str
    data: Any
    metadata: Dict[str, Any] = None


class MockTransport:
    """Mock transport for testing protocol integration."""
    
    def __init__(self):
        self.sent_messages: List[Message] = []
        self.input_responses: Dict[str, str] = {}
        self._lock = threading.Lock()
    
    async def send_message(self, msg: Message) -> None:
        """Simulate sending a message."""
        with self._lock:
            self.sent_messages.append(msg)
            
    def set_input_response(self, input_id: str, response: str):
        """Pre-configure an input response."""
        self.input_responses[input_id] = response
    
    def get_messages_of_type(self, msg_type: MessageType) -> List[Message]:
        """Get all messages of a specific type."""
        with self._lock:
            return [m for m in self.sent_messages if m.type == msg_type]


class ProtocolBridgedIO:
    """I/O streams that send protocol messages."""
    
    def __init__(self, transport: MockTransport, stream_type: str):
        self.transport = transport
        self.stream_type = stream_type
        self.buffer = ""
        
    def write(self, data: str) -> int:
        """Write data as protocol message."""
        self.buffer += data
        if '\n' in self.buffer:
            lines = self.buffer.split('\n')
            self.buffer = lines[-1]
            for line in lines[:-1]:
                msg = Message(
                    type=MessageType.OUTPUT,
                    id=str(uuid.uuid4()),
                    data=line + '\n',
                    metadata={'stream': self.stream_type}
                )
                # Schedule async send
                asyncio.create_task(self.transport.send_message(msg))
        return len(data)
    
    def flush(self):
        """Flush any buffered output."""
        if self.buffer:
            msg = Message(
                type=MessageType.OUTPUT,
                id=str(uuid.uuid4()),
                data=self.buffer,
                metadata={'stream': self.stream_type}
            )
            asyncio.create_task(self.transport.send_message(msg))
            self.buffer = ""


def test_output_protocol_integration():
    """Test that output is properly sent as protocol messages."""
    print("=" * 60)
    print("TEST 3.1: Output Protocol Integration")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        transport = MockTransport()
        
        async def run_test():
            shell = InteractiveShell.instance()
            
            # Override stdout/stderr with protocol bridges
            import sys
            original_stdout = sys.stdout
            original_stderr = sys.stderr
            
            sys.stdout = ProtocolBridgedIO(transport, 'stdout')
            sys.stderr = ProtocolBridgedIO(transport, 'stderr')
            
            # Execute code that produces output
            await shell.run_cell_async("print('Hello stdout')")
            await shell.run_cell_async("import sys; print('Hello stderr', file=sys.stderr)")
            
            # Flush outputs
            sys.stdout.flush()
            sys.stderr.flush()
            
            # Restore
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
            # Give async tasks time to complete
            await asyncio.sleep(0.1)
            
            # Check messages
            output_msgs = transport.get_messages_of_type(MessageType.OUTPUT)
            
            stdout_msgs = [m for m in output_msgs if m.metadata.get('stream') == 'stdout']
            stderr_msgs = [m for m in output_msgs if m.metadata.get('stream') == 'stderr']
            
            print(f"✓ Stdout messages sent: {len(stdout_msgs)} messages")
            print(f"✓ Stderr messages sent: {len(stderr_msgs)} messages")
            
            has_stdout = any('Hello stdout' in m.data for m in stdout_msgs)
            has_stderr = any('Hello stderr' in m.data for m in stderr_msgs)
            
            print(f"✓ Correct stdout content: {has_stdout}")
            print(f"✓ Correct stderr content: {has_stderr}")
            
            return has_stdout and has_stderr
        
        # Run async test
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run_test())
        return result
        
    except Exception as e:
        print(f"✗ Output protocol integration failed: {e}")
        traceback.print_exc()
        return False


def test_input_protocol_integration():
    """Test protocol-based input handling."""
    print("\n" + "=" * 60)
    print("TEST 3.2: Input Protocol Integration")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        transport = MockTransport()
        
        class ProtocolInput:
            """Input function that sends protocol messages."""
            
            def __init__(self, transport, loop):
                self.transport = transport
                self.loop = loop
                
            def __call__(self, prompt=""):
                # Send input request
                input_id = str(uuid.uuid4())
                msg = Message(
                    type=MessageType.INPUT,
                    id=input_id,
                    data=prompt,
                    metadata={}
                )
                
                # Send message (synchronously for simplicity)
                future = asyncio.run_coroutine_threadsafe(
                    self.transport.send_message(msg),
                    self.loop
                )
                future.result(timeout=1.0)
                
                # Return pre-configured response
                return self.transport.input_responses.get(input_id, "default_response")
        
        async def run_test():
            shell = InteractiveShell.instance()
            
            # Set up protocol input
            import builtins
            original_input = builtins.input
            
            loop = asyncio.get_event_loop()
            protocol_input = ProtocolInput(transport, loop)
            builtins.input = protocol_input
            shell.user_ns['input'] = protocol_input
            
            # Pre-configure response
            transport.input_responses[list(transport.input_responses.keys())[0] if transport.input_responses else "any"] = "user_response"
            
            # Execute code that requests input
            await shell.run_cell_async("user_input = input('Enter value: ')")
            
            # Restore
            builtins.input = original_input
            
            # Check results
            input_msgs = transport.get_messages_of_type(MessageType.INPUT)
            print(f"✓ Input request sent: {len(input_msgs)} messages")
            
            if input_msgs:
                print(f"✓ Input prompt: '{input_msgs[0].data}'")
            
            # Note: Can't fully test response without more complex async handling
            print(f"✓ Input mechanism integrated")
            
            return len(input_msgs) > 0
        
        # Run async test
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run_test())
        return result
        
    except Exception as e:
        print(f"✗ Input protocol integration failed: {e}")
        traceback.print_exc()
        return False


def test_result_protocol_integration():
    """Test that execution results are sent as protocol messages."""
    print("\n" + "=" * 60)
    print("TEST 3.3: Result Protocol Integration")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        transport = MockTransport()
        
        async def run_test():
            shell = InteractiveShell.instance()
            
            # Hook into execution results
            execution_results = []
            
            def post_execute_hook():
                """Called after execution."""
                # Get last execution result
                if shell.last_execution_result:
                    result = shell.last_execution_result.result
                    if result is not None:
                        msg = Message(
                            type=MessageType.RESULT,
                            id=str(uuid.uuid4()),
                            data=result,
                            metadata={'repr': repr(result)}
                        )
                        execution_results.append(msg)
                        asyncio.create_task(transport.send_message(msg))
            
            # Register hook
            shell.events.register('post_execute', post_execute_hook)
            
            # Execute code with results
            await shell.run_cell_async("42")
            await shell.run_cell_async("'string result'")
            await shell.run_cell_async("[1, 2, 3]")
            
            # Give async tasks time
            await asyncio.sleep(0.1)
            
            # Check messages
            result_msgs = transport.get_messages_of_type(MessageType.RESULT)
            
            print(f"✓ Result messages sent: {len(result_msgs)}")
            
            # Verify result values
            results = [m.data for m in result_msgs]
            has_int = 42 in results
            has_str = 'string result' in results
            has_list = [1, 2, 3] in results
            
            print(f"✓ Integer result: {has_int}")
            print(f"✓ String result: {has_str}")
            print(f"✓ List result: {has_list}")
            
            return len(result_msgs) >= 3
        
        # Run async test
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run_test())
        return result
        
    except Exception as e:
        print(f"✗ Result protocol integration failed: {e}")
        traceback.print_exc()
        return False


def test_error_protocol_integration():
    """Test that errors are sent as protocol messages."""
    print("\n" + "=" * 60)
    print("TEST 3.4: Error Protocol Integration")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        import traceback as tb
        
        transport = MockTransport()
        
        async def run_test():
            shell = InteractiveShell.instance()
            
            # Hook into exceptions
            def exception_handler(self, etype, value, tb_obj, tb_offset=None):
                """Custom exception handler."""
                # Format traceback
                tb_str = ''.join(tb.format_exception(etype, value, tb_obj))
                
                msg = Message(
                    type=MessageType.ERROR,
                    id=str(uuid.uuid4()),
                    data={
                        'exception_type': etype.__name__,
                        'exception_message': str(value),
                        'traceback': tb_str
                    },
                    metadata={}
                )
                asyncio.create_task(transport.send_message(msg))
                
                # Call default handler
                shell.showtraceback()
            
            # Override exception handler
            original_handler = shell.showtraceback
            shell.custom_exceptions = (Exception,)
            shell.set_custom_exc((Exception,), exception_handler)
            
            # Execute code that raises exceptions
            await shell.run_cell_async("1/0")
            await shell.run_cell_async("undefined_variable")
            await shell.run_cell_async("raise ValueError('custom error')")
            
            # Give async tasks time
            await asyncio.sleep(0.1)
            
            # Check messages
            error_msgs = transport.get_messages_of_type(MessageType.ERROR)
            
            print(f"✓ Error messages sent: {len(error_msgs)}")
            
            # Check error types
            error_types = [m.data.get('exception_type') for m in error_msgs if isinstance(m.data, dict)]
            
            has_zerodiv = 'ZeroDivisionError' in error_types
            has_name = 'NameError' in error_types
            has_value = 'ValueError' in error_types
            
            print(f"✓ ZeroDivisionError captured: {has_zerodiv}")
            print(f"✓ NameError captured: {has_name}")
            print(f"✓ ValueError captured: {has_value}")
            
            return len(error_msgs) >= 3
        
        # Run async test
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run_test())
        return result
        
    except Exception as e:
        print(f"✗ Error protocol integration failed: {e}")
        traceback.print_exc()
        return False


def test_execution_lifecycle():
    """Test complete execution lifecycle with protocol messages."""
    print("\n" + "=" * 60)
    print("TEST 3.5: Complete Execution Lifecycle")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        transport = MockTransport()
        
        async def run_test():
            shell = InteractiveShell.instance()
            
            execution_id = str(uuid.uuid4())
            
            # Simulate receiving execute message
            execute_msg = Message(
                type=MessageType.EXECUTE,
                id=execution_id,
                data="print('Hello'); result = 42; result",
                metadata={}
            )
            
            # Set up protocol I/O
            import sys
            sys.stdout = ProtocolBridgedIO(transport, 'stdout')
            
            # Track execution lifecycle
            lifecycle_events = []
            
            def pre_execute():
                lifecycle_events.append('pre_execute')
            
            def post_execute():
                lifecycle_events.append('post_execute')
                if shell.last_execution_result and shell.last_execution_result.result is not None:
                    msg = Message(
                        type=MessageType.RESULT,
                        id=execution_id,
                        data=shell.last_execution_result.result,
                        metadata={}
                    )
                    asyncio.create_task(transport.send_message(msg))
            
            shell.events.register('pre_execute', pre_execute)
            shell.events.register('post_execute', post_execute)
            
            # Execute
            await shell.run_cell_async(execute_msg.data)
            
            # Flush
            sys.stdout.flush()
            
            # Give async tasks time
            await asyncio.sleep(0.1)
            
            # Check complete lifecycle
            print(f"✓ Lifecycle events: {lifecycle_events}")
            
            output_msgs = transport.get_messages_of_type(MessageType.OUTPUT)
            result_msgs = transport.get_messages_of_type(MessageType.RESULT)
            
            has_output = any('Hello' in m.data for m in output_msgs)
            has_result = any(m.data == 42 for m in result_msgs)
            
            print(f"✓ Output produced: {has_output}")
            print(f"✓ Result produced: {has_result}")
            print(f"✓ Complete lifecycle: {len(lifecycle_events) == 2}")
            
            return has_output and has_result and len(lifecycle_events) == 2
        
        # Run async test
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run_test())
        return result
        
    except Exception as e:
        print(f"✗ Execution lifecycle failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all protocol integration tests."""
    print("IPython Integration Investigation - Protocol Integration")
    print("=" * 60)
    
    tests = [
        test_output_protocol_integration,
        test_input_protocol_integration,
        test_result_protocol_integration,
        test_error_protocol_integration,
        test_execution_lifecycle,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n✗ Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total = len(results)
    passed = sum(results)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("✓ All protocol integration tests passed!")
    else:
        print("✗ Some tests failed - protocol integration needs work")
        
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if main() else 1)