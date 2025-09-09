from __future__ import annotations

import asyncio
import contextlib
import sys
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from ..protocol.messages import (
    CancelMessage,
    ExecuteMessage,
    HeartbeatMessage,
    InputResponseMessage,
    InterruptMessage,
    Message,
    MessageType,
    ReadyMessage,
    ShutdownMessage,
)
from ..protocol.transport import PipeTransport
from .config import SessionConfig

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
    metadata: dict[str, Any] = field(default_factory=dict)


class Session:
    """Represents a single subprocess session."""

    def __init__(
        self,
        session_id: str | None = None,
        python_path: str = sys.executable,
        warmup_code: str | None = None,
        config: SessionConfig | None = None,
    ) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self._python_path = python_path
        self._warmup_code = warmup_code
        self._config = config or SessionConfig()
        self._process: asyncio.subprocess.Process | None = None
        self._transport: PipeTransport | None = None
        self._state = SessionState.CREATING
        self._info = SessionInfo(
            session_id=self.session_id,
            state=self._state,
            created_at=time.time(),
            last_used_at=time.time(),
        )
        self._lock = asyncio.Lock()
        self._ready_event = asyncio.Event()
        self._cancel_event = asyncio.Event()  # Event for cancellation
        self._message_handlers: dict[str, asyncio.Queue[Message]] = {}
        self._receive_task: asyncio.Task[None] | None = None
        # Interceptors invoked on every received message before routing
        self._interceptors: list[Callable[[Message], bool | None]] = []
        # Track routing tasks for observability and cleanup
        self._routing_tasks: set[asyncio.Task[None]] = set()

        # Metrics collection
        self._metrics = {
            "cancel_event_triggers": 0,
            "executions_cancelled": 0,
        }

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
        # Check process state and session state
        return self._process.returncode is None and self._state not in [
            SessionState.TERMINATED,
            SessionState.SHUTTING_DOWN,
            SessionState.ERROR,
            SessionState.CREATING,
        ]

    async def start(self) -> None:
        """Start the subprocess session."""
        async with self._lock:
            if self._state != SessionState.CREATING:
                raise RuntimeError(f"Cannot start session in state {self._state}")

            try:
                # Reset cancellation event for new lifecycle
                self._cancel_event = asyncio.Event()
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
                except TimeoutError as err:
                    await self.terminate()
                    raise RuntimeError("Session failed to become ready") from err

                self._state = SessionState.READY
                loop = asyncio.get_running_loop()
                logger.info(
                    "Session started",
                    session_id=self.session_id,
                    event_loop_id=id(loop),
                )

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

                # Invoke passive interceptors for all messages (including ready/heartbeat)
                if self._interceptors:
                    loop = asyncio.get_running_loop()
                    for interceptor in list(self._interceptors):
                        try:
                            logger.debug(
                                "message_interceptor_invoke",
                                session_id=self.session_id,
                                event_loop_id=id(loop),
                                message_type=getattr(message, "type", None),
                                execution_id=getattr(message, "execution_id", None),
                                interceptor=getattr(interceptor, "__name__", str(interceptor)),
                            )
                            _ = interceptor(message)
                        except Exception as e:
                            # Interceptors must never break routing; log and continue
                            logger.warning(
                                "message_interceptor_error",
                                error=str(e),
                                interceptor=getattr(interceptor, "__name__", str(interceptor)),
                            )

                # Handle different message types
                if message.type == "ready":
                    from typing import cast

                    ready_msg = cast(ReadyMessage, message)
                    logger.debug(
                        "Received ready message",
                        session_id=self.session_id,
                        capabilities=ready_msg.capabilities,
                    )
                    self._ready_event.set()

                elif message.type == "heartbeat":
                    from typing import cast

                    heartbeat = cast(HeartbeatMessage, message)
                    self._info.memory_usage = heartbeat.memory_usage
                    self._info.cpu_percent = heartbeat.cpu_percent

                else:
                    # Route to appropriate handler without blocking receive loop
                    t = asyncio.create_task(self._route_message(message))
                    self._routing_tasks.add(t)

                    def _done(task: asyncio.Task[None]) -> None:
                        self._routing_tasks.discard(task)
                        if task.cancelled():
                            return
                        exc = task.exception()
                        if exc:
                            logger.warning(
                                "route_message_task_error",
                                session_id=self.session_id,
                                error=str(exc),
                            )

                    t.add_done_callback(_done)

            except TimeoutError:
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
        # Interceptors are invoked in _receive_loop only to avoid double-calls

        # Check if message has execution_id and route to that execution's queue
        execution_id = getattr(message, "execution_id", None)
        if execution_id:
            handler_key = f"execution:{execution_id}"
            if handler_key in self._message_handlers:
                await self._message_handlers[handler_key].put(message)
                return

        # Otherwise use general queue
        if "general" not in self._message_handlers:
            self._message_handlers["general"] = asyncio.Queue()
        await self._message_handlers["general"].put(message)

    # --- Message interceptor API -------------------------------------------------
    def add_message_interceptor(self, fn: Callable[[Message], bool | None]) -> None:
        """Register a passive message interceptor.

        Interceptors are called for every received message on the session's event
        loop, before routing to internal queues. They must be non-blocking and
        must not consume messages. The return value is ignored.
        """
        if fn not in self._interceptors:
            self._interceptors.append(fn)

    def remove_message_interceptor(self, fn: Callable[[Message], bool | None]) -> None:
        """Unregister a previously added interceptor."""
        with contextlib.suppress(ValueError):
            self._interceptors.remove(fn)

    async def _wait_for_message_cancellable(
        self,
        queue: asyncio.Queue[Message],
        timeout: float | None = None,
    ) -> Message:
        """Wait for a message with cancellable timeout.

        This method provides an event-driven alternative to chunked timeouts,
        allowing for immediate cancellation response and reducing CPU wakeups.

        Args:
            queue: The message queue to wait on
            timeout: Optional timeout in seconds (uses monotonic time)

        Returns:
            The received message

        Raises:
            asyncio.TimeoutError: If timeout is reached
            asyncio.CancelledError: If session is cancelled/terminated
        """
        cancel_ev = self._cancel_event
        deadline = (time.monotonic() + timeout) if timeout else None

        queue_get = asyncio.create_task(queue.get())
        cancel_wait = asyncio.create_task(cancel_ev.wait())

        try:
            if deadline is not None:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Execution timeout")

                    done, _pending = await asyncio.wait(
                        {queue_get, cancel_wait},
                        timeout=remaining,
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if queue_get in done:
                        return queue_get.result()

                    if cancel_wait in done:
                        if self._config.enable_metrics:
                            self._metrics["cancel_event_triggers"] += 1
                        raise asyncio.CancelledError("Session cancelled/terminating")
            else:
                done, _ = await asyncio.wait(
                    {queue_get, cancel_wait}, return_when=asyncio.FIRST_COMPLETED
                )

                if queue_get in done:
                    return queue_get.result()
                else:
                    if self._config.enable_metrics:
                        self._metrics["cancel_event_triggers"] += 1
                    raise asyncio.CancelledError("Session cancelled/terminating")
        finally:
            # Clean up tasks
            for t in (queue_get, cancel_wait):
                if not t.done():
                    t.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await t

    async def execute(
        self,
        message: ExecuteMessage,
        timeout: float | None = 30.0,
    ) -> AsyncIterator[Message]:
        """Execute code and yield messages.

        Args:
            message: Execute message with code
            timeout: Execution timeout

        Yields:
            Messages from execution (output, result, error)
        """
        # Allow calls while BUSY; calls will serialize on the internal lock.
        if self._state in [
            SessionState.TERMINATED,
            SessionState.SHUTTING_DOWN,
            SessionState.ERROR,
            SessionState.CREATING,
        ]:
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
                    raise TimeoutError("Execution timeout")

                try:
                    # Wait for message using event-driven cancellable wait
                    queue = self._message_handlers[queue_key]
                    msg = await self._wait_for_message_cancellable(queue, timeout=remaining)

                    # Check if this is related to our execution
                    if (
                        hasattr(msg, "execution_id")
                        and getattr(msg, "execution_id", None) == execution_id
                    ):
                        yield msg

                        # Check if this completes the execution
                        # Note: InputMessage doesn't complete execution
                        if msg.type in [MessageType.RESULT, MessageType.ERROR]:
                            if msg.type == MessageType.ERROR:
                                self._info.error_count += 1
                            break
                        elif msg.type == MessageType.INPUT:
                            # Input request - continue waiting for more messages
                            continue

                except TimeoutError:
                    # Timeout means we hit the deadline
                    raise
                except asyncio.CancelledError:
                    # Session was cancelled/terminated
                    if self._config.enable_metrics:
                        self._metrics["executions_cancelled"] += 1
                    logger.debug(
                        "Execution cancelled via event",
                        session_id=self.session_id,
                        execution_id=execution_id,
                    )
                    raise

        finally:
            # Clean up message handler
            if queue_key in self._message_handlers:
                del self._message_handlers[queue_key]

            async with self._lock:
                # After an execution completes, return to READY state
                # READY represents an available, initialized session in this test suite
                self._state = SessionState.READY

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
        message_type: MessageType | None = None,
        timeout: float | None = None,
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
                raise TimeoutError("Receive timeout")

            try:
                # Use event-driven cancellable wait
                msg = await self._wait_for_message_cancellable(queue, timeout=remaining)

                if message_type is None or msg.type == message_type:
                    return msg

                # Put back if not matching type
                await queue.put(msg)

            except TimeoutError:
                raise
            except asyncio.CancelledError:
                # Session was cancelled/terminated
                logger.debug("Receive cancelled via event", session_id=self.session_id)
                raise

    async def shutdown(self, reason: str = "Requested", checkpoint: bool = True) -> None:
        """Gracefully shutdown the session.

        Args:
            reason: Shutdown reason
            checkpoint: Whether to create checkpoint before shutdown
        """
        if self._state == SessionState.TERMINATED:
            return

        # Set cancel event to interrupt any waiting operations
        self._cancel_event.set()

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
                    except TimeoutError:
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
        # Set cancel event to interrupt any waiting operations
        self._cancel_event.set()

        async with self._lock:
            self._state = SessionState.TERMINATED

        # Cancel receive task
        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task

        # Cancel any outstanding routing tasks
        if self._routing_tasks:
            for t in list(self._routing_tasks):
                t.cancel()
            for t in list(self._routing_tasks):
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            self._routing_tasks.clear()

        # Close transport
        if self._transport:
            try:
                await self._transport.close()
            except Exception as e:
                logger.debug(f"Error closing transport (non-critical): {e}")
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
