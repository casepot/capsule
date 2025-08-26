from __future__ import annotations

import asyncio
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, Optional

import structlog

from ..protocol.messages import (
    CancelMessage,
    ExecuteMessage,
    InputResponseMessage,
    InterruptMessage,
    Message,
    MessageType,
    ReadyMessage,
    ShutdownMessage,
)
from ..protocol.transport import PipeTransport

logger = structlog.get_logger()


class SessionState(str, Enum):
    """Session lifecycle states."""
    
    CREATING = "creating"
    WARMING = "warming"
    READY = "ready"
    BUSY = "busy"
    IDLE = "idle"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"
    TERMINATED = "terminated"


@dataclass
class SessionInfo:
    """Information about a session."""
    
    session_id: str
    state: SessionState
    created_at: float
    last_used_at: float
    execution_count: int = 0
    error_count: int = 0
    memory_usage: int = 0
    cpu_percent: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class Session:
    """Represents a single subprocess session."""
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        python_path: str = sys.executable,
        warmup_code: Optional[str] = None,
    ) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self._python_path = python_path
        self._warmup_code = warmup_code
        self._process: Optional[asyncio.subprocess.Process] = None
        self._transport: Optional[PipeTransport] = None
        self._state = SessionState.CREATING
        self._info = SessionInfo(
            session_id=self.session_id,
            state=self._state,
            created_at=time.time(),
            last_used_at=time.time(),
        )
        self._lock = asyncio.Lock()
        self._ready_event = asyncio.Event()
        self._message_handlers: Dict[str, asyncio.Queue[Message]] = {}
        self._receive_task: Optional[asyncio.Task[None]] = None
    
    @property
    def info(self) -> SessionInfo:
        """Get session information."""
        self._info.state = self._state
        return self._info
    
    @property
    def state(self) -> SessionState:
        """Get current session state."""
        return self._state
    
    @property
    def is_alive(self) -> bool:
        """Check if session process is alive."""
        if not self._process:
            return False
        return self._process.returncode is None
    
    async def start(self) -> None:
        """Start the subprocess session."""
        async with self._lock:
            if self._state != SessionState.CREATING:
                raise RuntimeError(f"Cannot start session in state {self._state}")
            
            try:
                # Start subprocess
                self._process = await asyncio.create_subprocess_exec(
                    self._python_path,
                    "-m",
                    "src.subprocess.worker",
                    self.session_id,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                
                # Create transport
                self._transport = PipeTransport(self._process, use_msgpack=True)
                await self._transport.start()
                
                # Start receive task
                self._receive_task = asyncio.create_task(self._receive_loop())
                
                # Wait for ready message
                self._state = SessionState.WARMING
                
                # Wait for ready with timeout
                try:
                    await asyncio.wait_for(self._ready_event.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    await self.terminate()
                    raise RuntimeError("Session failed to become ready")
                
                self._state = SessionState.READY
                logger.info("Session started", session_id=self.session_id)
                
            except Exception as e:
                self._state = SessionState.ERROR
                logger.error("Failed to start session", session_id=self.session_id, error=str(e))
                raise
        
        # Run warmup code if provided (outside lock to prevent deadlock)
        if self._warmup_code:
            await self._warmup()
    
    async def _warmup(self) -> None:
        """Run warmup code."""
        if not self._warmup_code:
            return
        
        logger.debug("Running warmup code", session_id=self.session_id)
        
        # Execute warmup code
        message = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code=self._warmup_code,
            capture_source=False,
        )
        
        async for _ in self.execute(message):
            pass  # Just consume messages during warmup
    
    async def _receive_loop(self) -> None:
        """Background task to receive messages from subprocess."""
        while self.is_alive and self._transport:
            try:
                message = await self._transport.receive_message(timeout=0.1)
                
                # Handle different message types
                if message.type == "ready":
                    ready_msg = message  # type: ignore
                    logger.debug(
                        "Received ready message",
                        session_id=self.session_id,
                        capabilities=ready_msg.capabilities,
                    )
                    self._ready_event.set()
                
                elif message.type == "heartbeat":
                    heartbeat = message  # type: ignore
                    self._info.memory_usage = heartbeat.memory_usage
                    self._info.cpu_percent = heartbeat.cpu_percent
                
                else:
                    # Route to appropriate handler
                    await self._route_message(message)
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self.is_alive:
                    logger.error(
                        "Receive loop error",
                        session_id=self.session_id,
                        error=str(e),
                    )
                break
    
    async def _route_message(self, message: Message) -> None:
        """Route message to appropriate handler.
        
        Args:
            message: Message to route
        """
        # Check if message has execution_id and route to that execution's queue
        execution_id = getattr(message, 'execution_id', None)
        if execution_id:
            handler_key = f"execution:{execution_id}"
            if handler_key in self._message_handlers:
                await self._message_handlers[handler_key].put(message)
                return
        
        # Otherwise use general queue
        if "general" not in self._message_handlers:
            self._message_handlers["general"] = asyncio.Queue()
        await self._message_handlers["general"].put(message)
    
    async def execute(
        self,
        message: ExecuteMessage,
        timeout: Optional[float] = 30.0,
    ) -> AsyncIterator[Message]:
        """Execute code and yield messages.
        
        Args:
            message: Execute message with code
            timeout: Execution timeout
            
        Yields:
            Messages from execution (output, result, error)
        """
        if self._state not in [SessionState.READY, SessionState.IDLE, SessionState.WARMING]:
            raise RuntimeError(f"Cannot execute in state {self._state}")
        
        if not self._transport:
            raise RuntimeError("Transport not initialized")
        
        async with self._lock:
            self._state = SessionState.BUSY
            self._info.last_used_at = time.time()
            self._info.execution_count += 1
        
        # Create message queue for this execution
        execution_id = message.id
        queue_key = f"execution:{execution_id}"
        self._message_handlers[queue_key] = asyncio.Queue()
        
        try:
            
            # Send execute message
            await self._transport.send_message(message)
            
            # Yield messages until we get result or error
            deadline = time.time() + timeout if timeout else None
            
            while True:
                remaining = (deadline - time.time()) if deadline else None
                if remaining is not None and remaining <= 0:
                    raise asyncio.TimeoutError("Execution timeout")
                
                try:
                    # Wait for message with timeout
                    queue = self._message_handlers[queue_key]
                    msg = await asyncio.wait_for(
                        queue.get(),
                        timeout=min(remaining, 1.0) if remaining else 1.0
                    )
                    
                    # Check if this is related to our execution
                    if hasattr(msg, "execution_id") and getattr(msg, "execution_id", None) == execution_id:
                        yield msg
                        
                        # Check if this completes the execution
                        if msg.type in [MessageType.RESULT, MessageType.ERROR]:
                            if msg.type == MessageType.ERROR:
                                self._info.error_count += 1
                            break
                    
                except asyncio.TimeoutError:
                    if deadline and time.time() >= deadline:
                        raise
                    continue
                    
        finally:
            # Clean up message handler
            if queue_key in self._message_handlers:
                del self._message_handlers[queue_key]
            
            async with self._lock:
                self._state = SessionState.IDLE
    
    async def send_message(self, message: Message) -> None:
        """Send a message to the subprocess.
        
        Args:
            message: Message to send
        """
        if not self._transport:
            raise RuntimeError("Transport not initialized")
        
        await self._transport.send_message(message)
    
    async def input_response(self, input_id: str, data: str) -> None:
        """Send input response to subprocess.
        
        Args:
            input_id: ID of the input request (from InputMessage)
            data: User's input data
        """
        response = InputResponseMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            data=data,
            input_id=input_id,
        )
        await self.send_message(response)
    
    async def cancel(self, execution_id: str, grace_timeout_ms: int = 500) -> bool:
        """Cancel a running execution.
        
        Args:
            execution_id: ID of the execution to cancel
            grace_timeout_ms: Grace period before hard cancel (default: 500ms)
            
        Returns:
            True if cancelled successfully, False if worker restart needed
        """
        if not self._transport:
            raise RuntimeError("Transport not initialized")
        
        # Send cancel message
        cancel_msg = CancelMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            execution_id=execution_id,
            grace_timeout_ms=grace_timeout_ms,
        )
        
        await self._transport.send_message(cancel_msg)
        
        # Wait for response or timeout
        grace_seconds = grace_timeout_ms / 1000.0
        start_time = time.time()
        
        # Check if worker is still alive after grace period
        while time.time() - start_time < grace_seconds + 1.0:  # Extra second for processing
            if not self.is_alive:
                # Worker died, needs restart
                logger.warning("Worker died during cancellation", session_id=self.session_id)
                return False
            
            await asyncio.sleep(0.01)
        
        return True
    
    async def interrupt(self, execution_id: str, force_restart: bool = False) -> None:
        """Immediately interrupt a running execution.
        
        Args:
            execution_id: ID of the execution to interrupt
            force_restart: Force worker restart after interrupt
        """
        if not self._transport:
            raise RuntimeError("Transport not initialized")
        
        # Send interrupt message
        interrupt_msg = InterruptMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            execution_id=execution_id,
            force_restart=force_restart,
        )
        
        await self._transport.send_message(interrupt_msg)
        
        if force_restart:
            # Wait a bit for graceful exit
            await asyncio.sleep(0.5)
            
            # Restart if needed
            if not self.is_alive:
                await self.restart()
    
    async def receive_message(
        self,
        message_type: Optional[MessageType] = None,
        timeout: Optional[float] = None,
    ) -> Message:
        """Receive a message from the subprocess.
        
        Args:
            message_type: Optional filter by message type
            timeout: Optional timeout
            
        Returns:
            Received message
        """
        queue_key = "general"
        
        if queue_key not in self._message_handlers:
            self._message_handlers[queue_key] = asyncio.Queue()
        
        queue = self._message_handlers[queue_key]
        
        deadline = time.time() + timeout if timeout else None
        
        while True:
            remaining = (deadline - time.time()) if deadline else None
            if remaining is not None and remaining <= 0:
                raise asyncio.TimeoutError("Receive timeout")
            
            try:
                msg = await asyncio.wait_for(
                    queue.get(),
                    timeout=remaining
                )
                
                if message_type is None or msg.type == message_type:
                    return msg
                
                # Put back if not matching type
                await queue.put(msg)
                
            except asyncio.TimeoutError:
                raise
    
    async def shutdown(self, reason: str = "Requested", checkpoint: bool = True) -> None:
        """Gracefully shutdown the session.
        
        Args:
            reason: Shutdown reason
            checkpoint: Whether to create checkpoint before shutdown
        """
        if self._state == SessionState.TERMINATED:
            return
        
        async with self._lock:
            self._state = SessionState.SHUTTING_DOWN
        
        try:
            if self._transport:
                # Send shutdown message
                shutdown_msg = ShutdownMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    reason=reason,
                    checkpoint=checkpoint,
                )
                
                await self._transport.send_message(shutdown_msg)
                
                # Wait for process to exit
                if self._process:
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Session did not shutdown gracefully",
                            session_id=self.session_id,
                        )
        
        except Exception as e:
            logger.error(
                "Error during shutdown",
                session_id=self.session_id,
                error=str(e),
            )
        
        finally:
            await self.terminate()
    
    async def terminate(self) -> None:
        """Forcefully terminate the session."""
        async with self._lock:
            self._state = SessionState.TERMINATED
        
        # Cancel receive task
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        # Close transport
        if self._transport:
            try:
                await self._transport.close()
            except:
                pass
            self._transport = None
        
        # Kill process if still running
        if self._process and self._process.returncode is None:
            self._process.kill()
            await self._process.wait()
        
        logger.info("Session terminated", session_id=self.session_id)
    
    async def restart(self) -> None:
        """Restart the session."""
        logger.info("Restarting session", session_id=self.session_id)
        
        # Terminate current process
        await self.terminate()
        
        # Reset state
        self._state = SessionState.CREATING
        self._ready_event.clear()
        
        # Start new process
        await self.start()