"""Thread-based execution for synchronous user code with async protocol I/O."""

from __future__ import annotations

import ast
import asyncio
import io
import sys
import threading
import time
import traceback
import uuid
from typing import Any, Dict, Optional

from ..protocol.messages import (
    InputMessage,
    OutputMessage,
    StreamType,
)
from ..protocol.transport import MessageTransport


class ThreadSafeOutput:
    """Bridge stdout/stderr from thread to async transport."""
    
    def __init__(self, executor: ThreadedExecutor, stream_type: StreamType) -> None:
        self._executor = executor
        self._stream_type = stream_type
        self._buffer = ""
        
    def write(self, data: str) -> int:
        """Write data and send complete lines to async transport."""
        if not isinstance(data, str):
            data = str(data)
            
        self._buffer += data
        
        # Send complete lines
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            # Schedule async send in main loop
            future = asyncio.run_coroutine_threadsafe(
                self._executor._send_output(line + '\n', self._stream_type),
                self._executor._loop
            )
            # Don't wait for completion to avoid blocking
            
        return len(data)
    
    def flush(self) -> None:
        """Flush any remaining buffer."""
        if self._buffer:
            future = asyncio.run_coroutine_threadsafe(
                self._executor._send_output(self._buffer, self._stream_type),
                self._executor._loop
            )
            self._buffer = ""
    
    def isatty(self) -> bool:
        return False
    
    def fileno(self) -> int:
        raise io.UnsupportedOperation("fileno")


class ThreadedExecutor:
    """Executes user code in thread with protocol-based I/O."""
    
    def __init__(
        self, 
        transport: MessageTransport, 
        execution_id: str, 
        namespace: Dict[str, Any],
        loop: asyncio.AbstractEventLoop
    ) -> None:
        self._transport = transport
        self._execution_id = execution_id
        self._namespace = namespace
        self._loop = loop  # Main async loop for coordination
        self._input_waiters: Dict[str, tuple[threading.Event, Optional[str]]] = {}
        self._result: Any = None
        self._error: Optional[Exception] = None
        
    def create_protocol_input(self) -> callable:
        """Create input function that works in thread context."""
        def protocol_input(prompt: str = "") -> str:
            """Input function that sends protocol message and waits for response."""
            # Generate unique token for this request
            token = str(uuid.uuid4())
            
            # Create event for synchronization
            event = threading.Event()
            self._input_waiters[token] = (event, None)
            
            # Schedule async message send in main loop
            future = asyncio.run_coroutine_threadsafe(
                self._send_input_request(token, prompt),
                self._loop
            )
            
            # Wait for send to complete
            try:
                future.result(timeout=5.0)
            except Exception as e:
                # Clean up on error
                self._input_waiters.pop(token, None)
                raise RuntimeError(f"Failed to send input request: {e}")
            
            # Block thread until response arrives
            if not event.wait(timeout=300):  # 5 minute timeout
                self._input_waiters.pop(token, None)
                raise TimeoutError("Input timeout exceeded")
            
            # Get the response value
            _, value = self._input_waiters.pop(token, (None, ""))
            return value or ""
            
        return protocol_input
    
    async def _send_input_request(self, token: str, prompt: str) -> None:
        """Send INPUT message (runs in async context)."""
        msg = InputMessage(
            id=token,
            timestamp=time.time(),
            prompt=prompt,
            execution_id=self._execution_id,
            timeout=None,  # Timeout handled at thread level
        )
        await self._transport.send_message(msg)
    
    async def _send_output(self, data: str, stream_type: StreamType) -> None:
        """Send output message (runs in async context)."""
        msg = OutputMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            data=data,
            stream=stream_type,
            execution_id=self._execution_id,
        )
        await self._transport.send_message(msg)
    
    def handle_input_response(self, token: str, data: str) -> None:
        """Handle input response from async context."""
        if token in self._input_waiters:
            event, _ = self._input_waiters[token]
            self._input_waiters[token] = (event, data)
            event.set()
    
    def execute_code(self, code: str) -> None:
        """Execute user code in thread context (called by thread)."""
        import builtins
        
        # Save originals
        original_input = builtins.input
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        try:
            # Override input
            builtins.input = self.create_protocol_input()
            self._namespace["input"] = builtins.input
            
            # Redirect output streams
            sys.stdout = ThreadSafeOutput(self, StreamType.STDOUT)
            sys.stderr = ThreadSafeOutput(self, StreamType.STDERR)
            
            # Parse code for source tracking (if needed)
            tree = ast.parse(code)
            
            # Execute the code
            compiled = compile(tree, "<session>", "exec")
            exec(compiled, self._namespace)
            
            # Try to capture result if it's an expression
            try:
                expr_tree = ast.parse(code, mode="eval")
                compiled_eval = compile(expr_tree, "<session>", "eval")
                self._result = eval(compiled_eval, self._namespace)
            except:
                # Not a single expression, no result to capture
                pass
                
        except Exception as e:
            # Store error for async context to handle
            self._error = e
            # Print traceback to stderr so it streams
            traceback.print_exc(file=sys.stderr)
            
        finally:
            # Flush any remaining output
            if hasattr(sys.stdout, 'flush'):
                sys.stdout.flush()
            if hasattr(sys.stderr, 'flush'):
                sys.stderr.flush()
                
            # Restore originals
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            builtins.input = original_input