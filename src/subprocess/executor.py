"""Thread-based execution for synchronous user code with async protocol I/O."""

from __future__ import annotations

import ast
import asyncio
import io
import queue
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
        """Write data to queue with proper line handling."""
        if not isinstance(data, str):
            data = str(data)
            
        self._buffer += data
        
        # Handle carriage returns for progress bars
        if '\r' in self._buffer:
            cr_parts = self._buffer.split('\r')
            # Keep only the last part after all CRs
            self._buffer = cr_parts[-1]
            # Send the last complete segment before the final CR
            for segment in cr_parts[:-1]:
                if segment:  # Don't send empty segments
                    try:
                        self._executor._output_queue.put((segment + '\r', self._stream_type), timeout=1.0)
                    except queue.Full:
                        # Drop output if queue is full (backpressure)
                        pass
        
        # Handle newlines
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            # Chunk very long lines to protect framing (64KB chunks)
            chunk_size = 64000
            if len(line) <= chunk_size:
                # Normal case: line fits in one chunk
                try:
                    self._executor._output_queue.put((line + '\n', self._stream_type), timeout=1.0)
                except queue.Full:
                    pass  # Drop if queue full
            else:
                # Long line: send in chunks
                for i in range(0, len(line), chunk_size):
                    chunk = line[i:i+chunk_size]
                    # Only add newline to last chunk
                    if i + chunk_size >= len(line):
                        chunk += '\n'
                    try:
                        self._executor._output_queue.put((chunk, self._stream_type), timeout=1.0)
                    except queue.Full:
                        break  # Stop chunking if queue full
            
        return len(data)
    
    def flush(self) -> None:
        """Flush any remaining buffer to the queue."""
        if self._buffer:
            try:
                self._executor._output_queue.put((self._buffer, self._stream_type), timeout=1.0)
            except queue.Full:
                pass  # Drop if queue full
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
        
        # Output queue and drain mechanism
        self._output_queue: queue.Queue = queue.Queue(maxsize=1024)
        self._pending_sends = 0
        self._drain_event: Optional[asyncio.Event] = None
        self._pump_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
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
    
    async def start_output_pump(self) -> None:
        """Start the async task that pumps output from queue to transport."""
        if self._drain_event is None:
            self._drain_event = asyncio.Event()
            self._drain_event.set()  # Initially nothing pending
        
        async def pump():
            """Pump output from queue to transport."""
            loop = asyncio.get_running_loop()
            
            while not self._shutdown:
                try:
                    # Use run_in_executor to read from blocking queue without freezing loop
                    # We need to handle queue.Empty exceptions properly
                    def get_from_queue():
                        try:
                            return self._output_queue.get(block=True, timeout=0.1)
                        except queue.Empty:
                            return 'QUEUE_EMPTY'  # Special marker for empty queue
                    
                    item = await loop.run_in_executor(None, get_from_queue)
                    
                    if item == 'QUEUE_EMPTY':
                        # Queue was empty, check if we should set drain event
                        if self._pending_sends == 0 and self._output_queue.empty():
                            self._drain_event.set()
                        continue
                    elif item is None:  # Sentinel for shutdown
                        break
                    
                    data, stream_type = item
                    
                    # Track pending sends
                    self._pending_sends += 1
                    self._drain_event.clear()
                    
                    try:
                        await self._send_output(data, stream_type)
                    finally:
                        self._pending_sends -= 1
                        # Set drain event if no more pending and queue empty
                        if self._pending_sends == 0 and self._output_queue.empty():
                            self._drain_event.set()
                            
                except Exception:
                    # Ignore exceptions and continue pumping
                    continue
            
            # Check drain event one more time when exiting
            if self._pending_sends == 0 and self._output_queue.empty():
                self._drain_event.set()
        
        self._pump_task = asyncio.create_task(pump())
    
    async def drain_outputs(self) -> None:
        """Wait for all pending outputs to be sent."""
        # If queue has items, give pump a brief moment to start processing
        if not self._output_queue.empty():
            await asyncio.sleep(0.005)  # 5ms should be enough
        
        if self._drain_event:
            await self._drain_event.wait()
    
    def shutdown_pump(self) -> None:
        """Signal the pump to shutdown."""
        self._shutdown = True
        # Put sentinel to unblock pump
        try:
            self._output_queue.put(None, block=False)
        except queue.Full:
            pass
    
    def handle_input_response(self, token: str, data: str) -> None:
        """Handle input response from async context."""
        if token in self._input_waiters:
            event, _ = self._input_waiters[token]
            self._input_waiters[token] = (event, data)
            event.set()
    
    def execute_code(self, code: str) -> None:
        """Execute user code in thread context (called by thread)."""
        import builtins
        
        # Save originals for stdout/stderr only (NOT input!)
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        try:
            # Only create protocol input if not already overridden
            if "input" not in self._namespace or not callable(self._namespace.get("input")):
                protocol_input = self.create_protocol_input()
                builtins.input = protocol_input
                self._namespace["input"] = protocol_input
                
                # Also override in builtins dict if present
                if "__builtins__" in self._namespace:
                    if isinstance(self._namespace["__builtins__"], dict):
                        self._namespace["__builtins__"]["input"] = protocol_input
                    else:
                        self._namespace["__builtins__"].input = protocol_input
            
            # Redirect output streams (these we DO restore)
            sys.stdout = ThreadSafeOutput(self, StreamType.STDOUT)
            sys.stderr = ThreadSafeOutput(self, StreamType.STDERR)
            
            # Decide once: expression vs statements
            # Expression iff parseable as eval mode
            is_expr = False
            try:
                ast.parse(code, mode="eval")
                is_expr = True
            except SyntaxError:
                is_expr = False
            
            # Execute code exactly once based on type
            if is_expr:
                # Single expression: evaluate and capture result
                compiled = compile(code, "<session>", "eval", dont_inherit=True, optimize=0)
                self._result = eval(compiled, self._namespace, self._namespace)
            else:
                # Statements: execute without result capture
                compiled = compile(code, "<session>", "exec", dont_inherit=True, optimize=0)
                exec(compiled, self._namespace, self._namespace)
                
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
                
            # Restore ONLY stdout/stderr, NOT input!
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            # DO NOT restore builtins.input - keep protocol override!