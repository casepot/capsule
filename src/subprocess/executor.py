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
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union, Literal

from ..protocol.messages import (
    InputMessage,
    OutputMessage,
    StreamType,
)
from ..protocol.transport import MessageTransport


# New types for event-driven output handling
@dataclass(slots=True)
class _OutputItem:
    """Output data to be sent."""
    data: str
    stream: StreamType


class _FlushSentinel:
    """Sentinel to mark execution boundary for draining."""
    __slots__ = ('future',)
    
    def __init__(self, future: asyncio.Future[None]) -> None:
        self.future = future


class _StopSentinel:
    """Sentinel to stop the pump task."""
    __slots__ = ()


# Union type for queue items
OutputOrSentinel = Union[_OutputItem, _FlushSentinel, _StopSentinel]


# Custom exceptions
class OutputBackpressureExceeded(RuntimeError):
    """Raised when output backpressure policy is exceeded."""
    pass


class OutputDrainTimeout(asyncio.TimeoutError):
    """Raised when drain operation times out."""
    pass


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
                    self._executor._enqueue_from_thread(segment + '\r', self._stream_type)
        
        # Handle newlines
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            # Chunk very long lines to protect framing (64KB chunks)
            chunk_size = self._executor._line_chunk_size
            if len(line) <= chunk_size:
                # Normal case: line fits in one chunk
                self._executor._enqueue_from_thread(line + '\n', self._stream_type)
            else:
                # Long line: send in chunks
                for i in range(0, len(line), chunk_size):
                    chunk = line[i:i+chunk_size]
                    # Only add newline to last chunk
                    if i + chunk_size >= len(line):
                        chunk += '\n'
                    self._executor._enqueue_from_thread(chunk, self._stream_type)
            
        return len(data)
    
    def flush(self) -> None:
        """Flush any remaining buffer to the queue."""
        if self._buffer:
            self._executor._enqueue_from_thread(self._buffer, self._stream_type)
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
        loop: asyncio.AbstractEventLoop,
        *,
        output_queue_maxsize: int = 1024,
        output_backpressure: Literal["block", "drop_new", "drop_oldest", "error"] = "block",
        line_chunk_size: int = 64 * 1024,
        drain_timeout_ms: Optional[int] = 2000,
    ) -> None:
        self._transport = transport
        self._execution_id = execution_id
        self._namespace = namespace
        self._loop = loop  # Main async loop for coordination
        self._input_waiters: Dict[str, tuple[threading.Event, Optional[str]]] = {}
        self._result: Any = None
        self._error: Optional[Exception] = None
        
        # Event-driven output handling with asyncio.Queue
        self._aq: asyncio.Queue[OutputOrSentinel] = asyncio.Queue(maxsize=output_queue_maxsize)
        self._drain_event: Optional[asyncio.Event] = None
        self._pump_task: Optional[asyncio.Task[None]] = None
        self._shutdown = False
        self._pending_sends = 0
        
        # Configuration
        self._line_chunk_size = line_chunk_size
        self._backpressure = output_backpressure
        self._drain_timeout = drain_timeout_ms / 1000.0 if drain_timeout_ms else None
        
        # Backpressure management
        self._capacity: Optional[threading.Semaphore] = (
            threading.Semaphore(output_queue_maxsize) if self._backpressure == "block" else None
        )
        
        # Metrics
        self._outputs_enqueued = 0
        self._outputs_sent = 0
        self._outputs_dropped = 0
        self._max_queue_depth = 0
        
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
    
    def _mark_not_drained_threadsafe(self) -> None:
        """Mark that new output is pending (safe to call from user thread)."""
        if self._drain_event:
            self._loop.call_soon_threadsafe(self._drain_event.clear)
    
    def _enqueue_from_thread(self, data: str, stream: StreamType) -> None:
        """Enqueue output from user thread with backpressure handling."""
        # Mark that we have pending output
        self._mark_not_drained_threadsafe()
        
        # Apply backpressure policy
        if self._capacity:
            # Block with bounded timeout to avoid permanent stalls
            if not self._capacity.acquire(timeout=2.0):
                # Timeout on acquire - apply policy
                if self._backpressure == "error":
                    raise OutputBackpressureExceeded("Capacity acquire timeout")
                self._outputs_dropped += 1
                return
        elif self._backpressure.startswith("drop"):
            # Check if queue is at capacity
            try:
                qsize = self._aq.qsize()
            except:
                qsize = 0  # Some platforms don't support qsize
                
            if qsize >= self._aq.maxsize:
                if self._backpressure == "drop_new":
                    self._outputs_dropped += 1
                    return
                elif self._backpressure == "drop_oldest":
                    # Try to remove one item (best effort)
                    def try_drop_oldest():
                        try:
                            self._aq.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    self._loop.call_soon_threadsafe(try_drop_oldest)
        elif self._backpressure == "error":
            try:
                qsize = self._aq.qsize()
            except:
                qsize = 0
            if qsize >= self._aq.maxsize:
                raise OutputBackpressureExceeded("Output queue full")
        
        # Update metrics
        self._outputs_enqueued += 1
        try:
            depth = self._aq.qsize() + 1
            if depth > self._max_queue_depth:
                self._max_queue_depth = depth
        except:
            pass  # qsize not supported on all platforms
        
        # Enqueue the item - wrap in a function to handle exceptions
        def safe_enqueue():
            try:
                self._aq.put_nowait(_OutputItem(data=data, stream=stream))
            except asyncio.QueueFull:
                # This shouldn't happen with our backpressure checks, but handle it
                self._outputs_dropped += 1
                if self._capacity:
                    self._capacity.release()
        
        self._loop.call_soon_threadsafe(safe_enqueue)
    
    async def start_output_pump(self) -> None:
        """Start the event-driven pump task."""
        if self._pump_task:
            return  # Already running
            
        self._drain_event = asyncio.Event()
        self._drain_event.set()  # Initially nothing pending
        self._shutdown = False
        
        async def pump() -> None:
            """Event-driven pump - no polling, awaits queue.get()."""
            try:
                while not self._shutdown:
                    # Await next item - no polling!
                    item = await self._aq.get()
                    
                    try:
                        if isinstance(item, _FlushSentinel):
                            # Flush barrier - signal completion if all sent
                            if self._pending_sends == 0 and self._aq.empty():
                                self._drain_event.set()
                            if not item.future.done():
                                item.future.set_result(None)
                            continue
                            
                        if isinstance(item, _StopSentinel):
                            break  # Shutdown requested
                            
                        # Regular output item
                        self._pending_sends += 1
                        try:
                            await self._send_output(item.data, item.stream)
                            self._outputs_sent += 1
                        finally:
                            self._pending_sends -= 1
                            if self._capacity:
                                self._capacity.release()
                            # Check if we're drained
                            if self._pending_sends == 0 and self._aq.empty():
                                self._drain_event.set()
                    finally:
                        self._aq.task_done()
            finally:
                # Ensure drain event is set on exit to prevent deadlock
                if self._drain_event and not self._drain_event.is_set():
                    self._drain_event.set()
        
        self._pump_task = asyncio.create_task(pump())
    
    async def drain_outputs(self, timeout: Optional[float] = None) -> None:
        """Wait for all pending outputs to be sent using flush sentinel."""
        if timeout is None:
            timeout = self._drain_timeout
            
        # Insert flush sentinel and wait for acknowledgment
        fut = self._loop.create_future()
        self._loop.call_soon_threadsafe(self._aq.put_nowait, _FlushSentinel(fut))
        
        try:
            await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as e:
            # Provide diagnostics on timeout
            pending = self._pending_sends
            try:
                qsize = self._aq.qsize()
            except:
                qsize = -1
            raise OutputDrainTimeout(
                f"drain_outputs timeout after {timeout}s "
                f"(pending_sends={pending}, queue_size={qsize}, "
                f"sent={self._outputs_sent}, dropped={self._outputs_dropped})"
            ) from e
    
    def shutdown_pump(self) -> None:
        """Signal the pump to shutdown."""
        self._shutdown = True
        # Put stop sentinel to cleanly exit pump
        self._loop.call_soon_threadsafe(self._aq.put_nowait, _StopSentinel())
    
    async def stop_output_pump(self) -> None:
        """Stop the output pump task."""
        if not self._pump_task:
            return
        self._shutdown = True
        self._loop.call_soon_threadsafe(self._aq.put_nowait, _StopSentinel())
        try:
            await asyncio.wait_for(self._pump_task, timeout=2.0)
        except asyncio.TimeoutError:
            self._pump_task.cancel()
        finally:
            self._pump_task = None
    
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