from __future__ import annotations

import ast
import asyncio
import io
import logging
import sys
import threading
import time
import traceback
import uuid
from typing import Any, Dict, Optional

import psutil
import structlog

# Configure logger to use stderr, not stdout
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    cache_logger_on_first_use=True,
)

from ..protocol.messages import (
    ErrorMessage,
    ExecuteMessage,
    HeartbeatMessage,
    InputMessage,
    InputResponseMessage,
    MessageType,
    OutputMessage,
    ReadyMessage,
    ResultMessage,
    StreamType,
)
from ..protocol.transport import MessageTransport
from .executor import ThreadedExecutor

logger = structlog.get_logger()


class OutputCapture:
    """Captures stdout/stderr and sends as output messages."""
    
    def __init__(
        self,
        transport: MessageTransport,
        execution_id: str,
        stream_type: StreamType,
    ) -> None:
        self._transport = transport
        self._execution_id = execution_id
        self._stream_type = stream_type
        self._buffer = io.StringIO()
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task[None]] = None
        
    async def write(self, data: str) -> None:
        """Write data to the capture buffer."""
        async with self._lock:
            self._buffer.write(data)
            
            # Start flush task if not running
            if not self._flush_task or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._flush())
    
    async def _flush(self) -> None:
        """Flush buffered output."""
        await asyncio.sleep(0.001)  # Small delay to batch writes
        
        async with self._lock:
            data = self._buffer.getvalue()
            if data:
                self._buffer = io.StringIO()
                
                # Send output message
                message = OutputMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    data=data,
                    stream=self._stream_type,
                    execution_id=self._execution_id,
                )
                
                try:
                    await self._transport.send_message(message)
                except Exception as e:
                    logger.error("Failed to send output", error=str(e))
    
    async def flush_final(self) -> None:
        """Final flush of any remaining output."""
        if self._flush_task:
            await self._flush_task
        
        async with self._lock:
            data = self._buffer.getvalue()
            if data:
                self._buffer = io.StringIO()
                
                message = OutputMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    data=data,
                    stream=self._stream_type,
                    execution_id=self._execution_id,
                )
                
                try:
                    await self._transport.send_message(message)
                except Exception as e:
                    logger.error("Failed to send final output", error=str(e))


class AsyncStdout:
    """Async wrapper for stdout."""
    
    def __init__(self, capture: OutputCapture) -> None:
        self._capture = capture
        self._write_tasks: list[asyncio.Task[None]] = []
        
    def write(self, data: str) -> int:
        """Write data asynchronously."""
        task = asyncio.create_task(self._capture.write(data))
        self._write_tasks.append(task)
        # Clean up completed tasks
        self._write_tasks = [t for t in self._write_tasks if not t.done()]
        return len(data)
    
    def flush(self) -> None:
        """Flush is handled automatically."""
        pass
    
    async def wait_for_writes(self) -> None:
        """Wait for all pending write tasks to complete."""
        if self._write_tasks:
            await asyncio.gather(*self._write_tasks, return_exceptions=True)


class InputHandler:
    """Handles input requests during execution."""
    
    def __init__(self, transport: MessageTransport, execution_id: str) -> None:
        self._transport = transport
        self._execution_id = execution_id
        
    async def request_input(self, prompt: str = "", timeout: Optional[float] = None) -> str:
        """Request input from the client.
        
        Args:
            prompt: Input prompt
            timeout: Optional timeout in seconds
            
        Returns:
            User input string
            
        Raises:
            TimeoutError: If timeout exceeded
        """
        # Send input request
        input_msg = InputMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            prompt=prompt,
            execution_id=self._execution_id,
            timeout=timeout,
        )
        
        await self._transport.send_message(input_msg)
        
        # Wait for response
        deadline = time.time() + timeout if timeout else None
        
        while True:
            remaining = (deadline - time.time()) if deadline else None
            if remaining is not None and remaining <= 0:
                raise TimeoutError("Input timeout exceeded")
            
            try:
                message = await self._transport.receive_message(timeout=remaining)
            except asyncio.TimeoutError:
                raise TimeoutError("Input timeout exceeded")
            
            if message.type == MessageType.INPUT_RESPONSE:
                response = message  # type: ignore
                if response.input_id == input_msg.id:
                    return response.data
            
            # Handle other messages while waiting
            # This ensures we don't block on input if other messages arrive


class SubprocessWorker:
    """Main subprocess worker that executes Python code."""
    
    def __init__(
        self,
        transport: MessageTransport,
        session_id: str,
    ) -> None:
        self._transport = transport
        self._session_id = session_id
        self._namespace: Dict[str, Any] = {}
        self._function_sources: Dict[str, str] = {}
        self._class_sources: Dict[str, str] = {}
        self._imports: list[str] = []
        self._running = False
        self._process = psutil.Process()
        self._active_executor: Optional[ThreadedExecutor] = None
        
        # Initialize namespace with builtins
        self._setup_namespace()
    
    def _setup_namespace(self) -> None:
        """Setup the initial namespace."""
        import builtins
        
        # Start with clean namespace
        self._namespace = {
            "__name__": "__main__",
            "__doc__": None,
            "__package__": None,
            "__loader__": None,
            "__spec__": None,
            "__annotations__": {},
            "__builtins__": builtins,
        }
    
    async def start(self) -> None:
        """Start the worker and send ready message."""
        self._running = True
        
        # Send ready message
        ready_msg = ReadyMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            session_id=self._session_id,
            capabilities=[
                "execute",
                "input",
                "checkpoint",
                "restore",
                "transactions",
                "source_tracking",
            ],
        )
        
        await self._transport.send_message(ready_msg)
        
        # Start heartbeat task
        asyncio.create_task(self._heartbeat_loop())
    
    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages."""
        while self._running:
            try:
                # Get memory usage
                mem_info = self._process.memory_info()
                cpu_percent = self._process.cpu_percent()
                
                heartbeat = HeartbeatMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    memory_usage=mem_info.rss,
                    cpu_percent=cpu_percent,
                    namespace_size=len(self._namespace),
                )
                
                await self._transport.send_message(heartbeat)
                
            except Exception as e:
                logger.error("Heartbeat error", error=str(e))
            
            await asyncio.sleep(5.0)
    
    async def execute(self, message: ExecuteMessage) -> None:
        """Execute Python code using threaded executor.
        
        Args:
            message: Execute message with code to run
        """
        execution_id = message.id
        start_time = time.time()
        
        # Get the current event loop for thread coordination
        loop = asyncio.get_running_loop()
        
        # Create threaded executor
        executor = ThreadedExecutor(
            self._transport,
            execution_id,
            self._namespace,
            loop
        )
        
        # Track active executor for input routing
        self._active_executor = executor
        logger.debug("Set active executor", execution_id=execution_id)
        
        # Parse code for source tracking before execution
        if message.capture_source:
            self._track_sources(message.code)
        
        # Track imports
        self._track_imports(message.code)
        
        # Create and start execution thread
        thread = threading.Thread(
            target=executor.execute_code,
            args=(message.code,),
            name=f"exec-{execution_id}",
            daemon=True
        )
        
        thread.start()
        
        try:
            # Monitor thread while staying responsive to async events
            while thread.is_alive():
                await asyncio.sleep(0.001)  # Small sleep to stay responsive
                
            # Wait for thread to fully complete
            thread.join(timeout=1.0)
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Check if there was an error
            if executor._error:
                # Error already printed to stderr by executor
                error_msg = ErrorMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    traceback="".join(traceback.format_exception(type(executor._error), executor._error, executor._error.__traceback__)),
                    exception_type=type(executor._error).__name__,
                    exception_message=str(executor._error),
                    execution_id=execution_id,
                )
                await self._transport.send_message(error_msg)
            else:
                # Send result
                if executor._result is not None:
                    result_msg = ResultMessage(
                        id=str(uuid.uuid4()),
                        timestamp=time.time(),
                        value=executor._result if self._is_json_serializable(executor._result) else None,
                        repr=repr(executor._result),
                        execution_id=execution_id,
                        execution_time=execution_time,
                    )
                    await self._transport.send_message(result_msg)
                else:
                    # Send empty result to indicate completion
                    result_msg = ResultMessage(
                        id=str(uuid.uuid4()),
                        timestamp=time.time(),
                        value=None,
                        repr="",
                        execution_id=execution_id,
                        execution_time=execution_time,
                    )
                    await self._transport.send_message(result_msg)
                    
        except Exception as e:
            # Send error for any execution management issues
            error_msg = ErrorMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                traceback=traceback.format_exc(),
                exception_type=type(e).__name__,
                exception_message=str(e),
                execution_id=execution_id,
            )
            await self._transport.send_message(error_msg)
            
        finally:
            # Clear active executor
            logger.debug("Clearing active executor", execution_id=execution_id)
            self._active_executor = None
    
    def _track_sources(self, code: str) -> None:
        """Track function and class sources from code.
        
        Args:
            code: Python code to analyze
        """
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self._function_sources[node.name] = ast.unparse(node)
                elif isinstance(node, ast.ClassDef):
                    self._class_sources[node.name] = ast.unparse(node)
                    
        except Exception as e:
            logger.error("Failed to track sources", error=str(e))
    
    def _track_imports(self, code: str) -> None:
        """Track import statements from code.
        
        Args:
            code: Python code to analyze
        """
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    import_str = ast.unparse(node)
                    if import_str not in self._imports:
                        self._imports.append(import_str)
                        
        except Exception as e:
            logger.error("Failed to track imports", error=str(e))
    
    def _is_json_serializable(self, obj: Any) -> bool:
        """Check if object is JSON serializable.
        
        Args:
            obj: Object to check
            
        Returns:
            True if JSON serializable
        """
        import json
        
        try:
            json.dumps(obj)
            return True
        except (TypeError, ValueError):
            return False
    
    async def run(self) -> None:
        """Main execution loop."""
        await self.start()
        
        while self._running:
            try:
                # Receive message
                logger.debug("Worker waiting for message...")
                message = await self._transport.receive_message()
                logger.info("Worker received message", type=message.type, id=message.id, type_value=str(message.type), type_class=type(message.type).__name__, has_executor=self._active_executor is not None)
                
                # Handle message based on type
                # Check both string and enum comparison for debugging
                logger.debug(f"Checking message type: {message.type} == {MessageType.EXECUTE} ? {message.type == MessageType.EXECUTE}")
                logger.debug(f"Checking string comparison: {message.type} == 'execute' ? {message.type == 'execute'}")
                
                if message.type == MessageType.EXECUTE or message.type == "execute":
                    logger.info("Processing execute message", id=message.id)
                    # Don't await - let it run in background so we can process INPUT_RESPONSE
                    asyncio.create_task(self.execute(message))  # type: ignore
                    
                elif message.type == MessageType.INPUT_RESPONSE or message.type == "input_response":
                    # Route input response to active executor
                    if self._active_executor:
                        response = message  # type: ignore
                        logger.debug("Routing input response", token=response.input_id, data=response.data)
                        self._active_executor.handle_input_response(response.input_id, response.data)
                    else:
                        logger.warning("Received input response with no active executor")
                    
                elif message.type == MessageType.CHECKPOINT:
                    # Will be implemented with checkpoint system
                    pass
                    
                elif message.type == MessageType.RESTORE:
                    # Will be implemented with restore system
                    pass
                    
                elif message.type == MessageType.SHUTDOWN:
                    shutdown_msg = message  # type: ignore
                    logger.info("Shutdown requested", reason=shutdown_msg.reason)
                    self._running = False
                    break
                    
            except Exception as e:
                logger.error("Worker error", error=str(e))
                
                # Send error message
                error_msg = ErrorMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    traceback=traceback.format_exc(),
                    exception_type=type(e).__name__,
                    exception_message=str(e),
                    execution_id=None,
                )
                
                try:
                    await self._transport.send_message(error_msg)
                except:
                    pass  # Failed to send error
    
    async def stop(self) -> None:
        """Stop the worker."""
        self._running = False


async def main() -> None:
    """Main entry point for subprocess worker."""
    import sys
    
    # Get session ID from command line
    if len(sys.argv) < 2:
        logger.error("Session ID required")
        sys.exit(1)
    
    session_id = sys.argv[1]
    
    # Create transport using stdin/stdout
    # Get the event loop
    loop = asyncio.get_event_loop()
    
    # Create reader from stdin (use buffer for binary)
    reader = asyncio.StreamReader()
    reader_protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin.buffer)
    
    # Create writer from stdout (use buffer for binary)
    # Need to use StreamReaderProtocol for proper drain support
    writer_transport, writer_protocol = await loop.connect_write_pipe(
        lambda: asyncio.StreamReaderProtocol(asyncio.StreamReader()), 
        sys.stdout.buffer
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)
    
    transport = MessageTransport(
        reader=reader,
        writer=writer,
        use_msgpack=True,
    )
    
    # Start the transport to begin the background reader task
    await transport.start()
    
    # Create and run worker
    worker = SubprocessWorker(transport, session_id)
    
    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Worker interrupted")
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())