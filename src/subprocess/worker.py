from __future__ import annotations

import ast
import asyncio
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
    ReadyMessage,
    ResultMessage,
)
from ..protocol.transport import MessageTransport
from .executor import ThreadedExecutor, OutputDrainTimeout
from .constants import ENGINE_INTERNALS

logger = structlog.get_logger()


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
            
            if message.type == "input_response":
                response = message  # type: ignore
                if response.input_id == input_msg.id:
                    return response.data
            
            # Handle other messages while waiting
            # This ensures we don't block on input if other messages arrive


class SubprocessWorker:
    """Main subprocess worker that executes Python code."""
    
    # Engine internals imported from constants module
    # See constants.py for the complete list and documentation
    
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
        self._active_thread: Optional[threading.Thread] = None
        
        # Initialize namespace with builtins
        self._setup_namespace()
    
    def _setup_namespace(self) -> None:
        """Setup the initial namespace.
        
        CRITICAL: Never replace namespace, always merge/update to preserve
        engine internals and prevent KeyError failures.
        """
        import builtins
        
        # CRITICAL: Never replace, always update (spec line 22)
        # Update with required built-ins instead of replacing
        self._namespace.update({
            "__name__": "__main__",
            "__doc__": None,
            "__package__": None,
            "__loader__": None,
            "__spec__": None,
            "__annotations__": {},
            "__builtins__": builtins,
        })
        
        # Initialize engine internals with proper defaults
        for key in ENGINE_INTERNALS:
            if key not in self._namespace:
                if key in ['Out', '_oh']:
                    self._namespace[key] = {}
                elif key in ['In', '_ih']:
                    self._namespace[key] = []
                else:
                    self._namespace[key] = None
    
    async def _cancel_with_timeout(self, execution_id: str, grace_timeout_ms: int, thread: threading.Thread = None) -> bool:
        """Cancel execution with grace period before hard cancel.
        
        Args:
            execution_id: Execution to cancel
            grace_timeout_ms: Milliseconds to wait before hard cancel
            
        Returns:
            True if cancelled cooperatively, False if hard cancel needed
        """
        logger.info(f"_cancel_with_timeout called for {execution_id}, active: {self._active_executor is not None}")
        
        if not self._active_executor or self._active_executor.execution_id != execution_id:
            logger.info(f"Not our execution - active_id={self._active_executor.execution_id if self._active_executor else None}")
            return True  # Not our execution
        
        # Request cooperative cancellation
        self._active_executor.cancel()
        
        # Wait for grace period
        grace_seconds = grace_timeout_ms / 1000.0
        start_time = time.time()
        
        while time.time() - start_time < grace_seconds:
            # Check if execution finished
            # If thread was provided, check if it's still alive
            if thread and not thread.is_alive():
                logger.info(f"Thread finished for {execution_id}")
                return True  # Cancelled successfully
            # Otherwise check if executor was cleared (backward compatibility)
            executor = self._active_executor
            if executor is None or executor.execution_id != execution_id:
                return True  # Cancelled successfully
            
            await asyncio.sleep(0.01)  # Check every 10ms
        
        # Grace period expired, need hard cancel
        logger.warning(
            "Grace period expired, hard cancel required",
            execution_id=execution_id,
            grace_ms=grace_timeout_ms
        )
        return False
    
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
        logger.info(f"execute() method started for {execution_id}")
        
        # Get the current event loop for thread coordination
        loop = asyncio.get_running_loop()
        
        # Create threaded executor with configurable timeouts
        executor = ThreadedExecutor(
            self._transport,
            execution_id,
            self._namespace,
            loop,
            input_send_timeout=5.0,  # TODO: Make configurable via session config
            input_wait_timeout=300.0  # TODO: Make configurable via session config
        )
        
        # Start output pump for async message sending
        await executor.start_output_pump()
        
        # Track active executor for input routing
        self._active_executor = executor
        logger.info(f"Set active executor to {execution_id}, executor.execution_id={executor.execution_id}")
        
        # Parse code for source tracking before execution
        if message.capture_source:
            self._track_sources(message.code)
        
        # Track imports
        self._track_imports(message.code)
        
        # Create and start execution thread
        # The tracer will be set inside execute_code() using sys.settrace
        thread = threading.Thread(
            target=executor.execute_code,
            args=(message.code,),
            name=f"exec-{execution_id}",
            daemon=True
        )
        
        thread.start()
        logger.info(f"Started execution thread for {execution_id}, thread alive={thread.is_alive()}")
        
        # Store thread reference for cancellation checks
        self._active_thread = thread
        
        try:
            # Monitor thread while staying responsive to async events
            while thread.is_alive():
                await asyncio.sleep(0.001)  # Small sleep to stay responsive
                
            # Wait for thread to fully complete
            thread.join(timeout=1.0)
            logger.info(f"Thread joined for {execution_id}, error={executor.error}")
            
            # CRITICAL: Drain all outputs before sending result
            # This ensures output messages arrive before ResultMessage
            try:
                # Use a reasonable timeout (default is 2 seconds from executor)
                await executor.drain_outputs(timeout=5.0)
            except OutputDrainTimeout as e:
                # Log the timeout but don't fail the execution
                logger.warning(
                    "Output drain timeout",
                    execution_id=execution_id,
                    error=str(e)
                )
                # Send error about the timeout
                error_msg = ErrorMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    traceback=str(e),
                    exception_type="OutputDrainTimeout",
                    exception_message="Failed to drain all outputs before timeout",
                    execution_id=execution_id,
                )
                await self._transport.send_message(error_msg)
                # Don't send ResultMessage if drain failed - maintain ordering guarantee
                return
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Check if there was an error
            if executor.error:
                logger.info(f"Sending ErrorMessage for {execution_id}: {type(executor.error).__name__}")
                # Error already printed to stderr by executor
                error_msg = ErrorMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    traceback="".join(traceback.format_exception(type(executor.error), executor.error, executor.error.__traceback__)),
                    exception_type=type(executor.error).__name__,
                    exception_message=str(executor.error),
                    execution_id=execution_id,
                )
                await self._transport.send_message(error_msg)
            else:
                # Send result
                if executor.result is not None:
                    result_msg = ResultMessage(
                        id=str(uuid.uuid4()),
                        timestamp=time.time(),
                        value=executor.result if self._is_json_serializable(executor.result) else None,
                        repr=repr(executor.result),
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
            # Shutdown input waiters before cleaning up  
            executor.shutdown_input_waiters()
            
            # Shutdown output pump and clean up
            executor.shutdown_pump()
            if executor.pump_task:
                try:
                    await asyncio.wait_for(executor.pump_task, timeout=1.0)
                except asyncio.TimeoutError:
                    pass  # Force continue if pump doesn't stop
            
            # Clear active executor and thread
            logger.debug("Clearing active executor", execution_id=execution_id)
            self._active_executor = None
            self._active_thread = None
    
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
                logger.debug(f"Processing message with type: {message.type}")
                
                # Convert to string for comparison (MessageType enum)
                msg_type = str(message.type) if hasattr(message.type, 'value') else message.type
                logger.debug(f"Message type for comparison: {msg_type} (original: {message.type})")
                
                if msg_type == "execute" or message.type == MessageType.EXECUTE:
                    logger.info("Processing execute message", id=message.id)
                    # Don't await - let it run in background so we can process INPUT_RESPONSE
                    exec_task = asyncio.create_task(self.execute(message))  # type: ignore
                    logger.info(f"Created execution task for {message.id}")
                    
                elif msg_type == "input_response" or message.type == MessageType.INPUT_RESPONSE:
                    # Route input response to active executor
                    if self._active_executor:
                        if isinstance(message, InputResponseMessage):
                            logger.debug("Routing input response", token=message.input_id, data=message.data)
                            self._active_executor.handle_input_response(message.input_id, message.data)
                        else:
                            logger.warning("Unexpected message type for input_response")
                    else:
                        logger.warning("Received input response with no active executor")
                    
                elif msg_type == "checkpoint" or message.type == MessageType.CHECKPOINT:
                    # Will be implemented with checkpoint system
                    pass
                    
                elif msg_type == "restore" or message.type == MessageType.RESTORE:
                    # Will be implemented with restore system
                    pass
                    
                elif msg_type == "cancel" or message.type == MessageType.CANCEL:
                    # Handle cancellation request
                    cancel_msg = message  # type: ignore
                    logger.info("Cancel requested", execution_id=cancel_msg.execution_id, 
                               has_active_executor=self._active_executor is not None,
                               active_exec_id=self._active_executor.execution_id if self._active_executor else None)
                    
                    # Cancel with grace period
                    grace_ms = cancel_msg.grace_timeout_ms or 500
                    cancelled = await self._cancel_with_timeout(cancel_msg.execution_id, grace_ms, self._active_thread)
                    
                    if not cancelled:
                        # Hard cancel required - restart worker
                        logger.error("Hard cancel required, exiting worker for restart")
                        self._running = False
                        break
                        
                elif msg_type == "interrupt" or message.type == MessageType.INTERRUPT:
                    # Handle interrupt request (immediate)
                    interrupt_msg = message  # type: ignore
                    logger.info("Interrupt requested", execution_id=interrupt_msg.execution_id, force_restart=interrupt_msg.force_restart)
                    
                    if self._active_executor and self._active_executor.execution_id == interrupt_msg.execution_id:
                        # Cancel the active execution
                        self._active_executor.cancel()
                        
                        # If force_restart is set, we should restart the worker
                        # This would be handled at the session level
                        if interrupt_msg.force_restart:
                            logger.warning("Force restart requested, exiting worker")
                            self._running = False
                            break
                    
                elif msg_type == "shutdown" or message.type == MessageType.SHUTDOWN:
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
    # Get the event loop created by asyncio.run()
    loop = asyncio.get_running_loop()
    
    logger.info(
        "worker_start",
        session_id=session_id,
        event_loop_id=id(loop),
        python_version=sys.version,
        pid=sys.platform != 'win32' and psutil.Process().pid or None
    )
    
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