from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

import structlog

from .manager import Session, SessionState

logger = structlog.get_logger()


@dataclass
class PoolConfig:
    """Configuration for session pool."""
    
    min_idle: int = 2
    max_sessions: int = 10
    session_timeout: float = 300.0  # 5 minutes idle timeout
    warmup_code: Optional[str] = None
    health_check_interval: float = 30.0
    pre_warm_on_start: bool = True
    recycle_after_executions: int = 100


class SessionPool:
    """Manages a pool of subprocess sessions with pre-warming."""
    
    def __init__(
        self,
        config: Optional[PoolConfig] = None,
        *,
        min_idle: Optional[int] = None,
        max_sessions: Optional[int] = None,
        session_timeout: Optional[float] = None,
        warmup_code: Optional[str] = None,
        health_check_interval: Optional[float] = None,
        pre_warm_on_start: Optional[bool] = None,
        recycle_after_executions: Optional[int] = None,
        # Support legacy parameter names for compatibility
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
    ) -> None:
        if config:
            self._config = config
        else:
            self._config = PoolConfig()
            # Apply keyword arguments if provided
            if min_idle is not None:
                self._config.min_idle = min_idle
            elif min_size is not None:  # Support legacy name
                self._config.min_idle = min_size
            
            if max_sessions is not None:
                self._config.max_sessions = max_sessions
            elif max_size is not None:  # Support legacy name
                self._config.max_sessions = max_size
            
            if session_timeout is not None:
                self._config.session_timeout = session_timeout
            if warmup_code is not None:
                self._config.warmup_code = warmup_code
            if health_check_interval is not None:
                self._config.health_check_interval = health_check_interval
            if pre_warm_on_start is not None:
                self._config.pre_warm_on_start = pre_warm_on_start
            if recycle_after_executions is not None:
                self._config.recycle_after_executions = recycle_after_executions
        self._idle_sessions: asyncio.Queue[Session] = asyncio.Queue()
        self._active_sessions: Set[Session] = set()
        self._all_sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._shutdown = False
        self._warmup_task: Optional[asyncio.Task[None]] = None
        self._health_check_task: Optional[asyncio.Task[None]] = None
        self._metrics = PoolMetrics()
    
    async def start(self) -> None:
        """Start the session pool."""
        logger.info(
            "Starting session pool",
            min_idle=self._config.min_idle,
            max_sessions=self._config.max_sessions,
        )
        
        # Pre-warm sessions if configured
        if self._config.pre_warm_on_start:
            await self.ensure_min_sessions()
        
        # Start background tasks
        self._warmup_task = asyncio.create_task(self._warmup_loop())
        self._health_check_task = asyncio.create_task(self._health_check_loop())
    
    async def stop(self) -> None:
        """Stop the session pool and cleanup all sessions."""
        logger.info("Stopping session pool")
        self._shutdown = True
        
        # Cancel background tasks
        if self._warmup_task:
            self._warmup_task.cancel()
            try:
                await self._warmup_task
            except asyncio.CancelledError:
                pass
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Shutdown all sessions
        tasks = []
        for session in self._all_sessions.values():
            tasks.append(asyncio.create_task(session.shutdown("Pool shutdown")))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self._all_sessions.clear()
        self._active_sessions.clear()
    
    async def acquire(self, timeout: Optional[float] = None) -> Session:
        """Acquire a session from the pool.
        
        Args:
            timeout: Optional timeout for acquisition
            
        Returns:
            Available session
            
        Raises:
            TimeoutError: If timeout exceeded
        """
        start_time = time.time()
        self._metrics.acquisition_attempts += 1
        
        deadline = time.time() + timeout if timeout else None
        
        while not self._shutdown:
            # Try to get idle session
            try:
                session = self._idle_sessions.get_nowait()
                
                # Check if session is still alive
                if session.is_alive:
                    async with self._lock:
                        self._active_sessions.add(session)
                    
                    self._metrics.acquisition_success += 1
                    self._metrics.total_acquisition_time += time.time() - start_time
                    self._metrics.pool_hits += 1
                    
                    logger.debug(
                        "Acquired session from pool",
                        session_id=session.session_id,
                        acquisition_time=time.time() - start_time,
                    )
                    
                    return session
                else:
                    # Session is dead, remove it
                    await self._remove_session(session)
                    
            except asyncio.QueueEmpty:
                pass
            
            # Check if we can create new session
            async with self._lock:
                total_sessions = len(self._all_sessions)
                can_create = total_sessions < self._config.max_sessions
            
            if can_create:
                # Create new session without holding lock
                session = await self._create_session()
                
                async with self._lock:
                    self._active_sessions.add(session)
                
                self._metrics.acquisition_success += 1
                self._metrics.total_acquisition_time += time.time() - start_time
                self._metrics.pool_misses += 1
                
                logger.debug(
                    "Created new session",
                    session_id=session.session_id,
                    acquisition_time=time.time() - start_time,
                )
                
                return session
            
            # Wait for session to become available
            if deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._metrics.acquisition_timeouts += 1
                    raise TimeoutError("Session acquisition timeout")
                
                try:
                    session = await asyncio.wait_for(
                        self._idle_sessions.get(),
                        timeout=remaining
                    )
                except asyncio.TimeoutError:
                    self._metrics.acquisition_timeouts += 1
                    raise TimeoutError("Session acquisition timeout")
            else:
                # Wait indefinitely
                session = await self._idle_sessions.get()
            
            # Verify session is alive
            if session.is_alive:
                async with self._lock:
                    self._active_sessions.add(session)
                
                self._metrics.acquisition_success += 1
                self._metrics.total_acquisition_time += time.time() - start_time
                self._metrics.pool_hits += 1
                
                return session
            else:
                await self._remove_session(session)
        
        raise RuntimeError("Pool is shutting down")
    
    async def release(self, session: Session, restart_if_dead: bool = True) -> None:
        """Release a session back to the pool.
        
        Args:
            session: Session to release
            restart_if_dead: Whether to restart session if it's dead
        """
        async with self._lock:
            if session in self._active_sessions:
                self._active_sessions.remove(session)
        
        # Check if session should be recycled
        if session.info.execution_count >= self._config.recycle_after_executions:
            logger.info(
                "Recycling session due to execution count",
                session_id=session.session_id,
                execution_count=session.info.execution_count,
            )
            await self._recycle_session(session)
            return
        
        # Check if session is still healthy
        if not session.is_alive or session.state == SessionState.ERROR:
            logger.warning(
                "Released session is not healthy",
                session_id=session.session_id,
                state=session.state,
            )
            
            if restart_if_dead:
                # Try to restart the session
                try:
                    logger.info("Attempting to restart dead session", session_id=session.session_id)
                    await session.restart()
                    
                    # Return to idle pool if restart succeeded
                    await self._idle_sessions.put(session)
                    self._metrics.sessions_restarted += 1
                    logger.info("Session restarted and returned to pool", session_id=session.session_id)
                    return
                except Exception as e:
                    logger.error("Failed to restart session", session_id=session.session_id, error=str(e))
            
            await self._remove_session(session)
            return
        
        # Return to idle pool
        await self._idle_sessions.put(session)
        
        logger.debug(
            "Released session to pool",
            session_id=session.session_id,
            idle_count=self._idle_sessions.qsize(),
        )
    
    async def _create_session(self) -> Session:
        """Create a new session.
        
        Returns:
            New session
        """
        session = Session(warmup_code=self._config.warmup_code)
        
        # Start session
        await session.start()
        
        # Register session
        async with self._lock:
            self._all_sessions[session.session_id] = session
        
        self._metrics.sessions_created += 1
        
        logger.info(
            "Created session",
            session_id=session.session_id,
            total_sessions=len(self._all_sessions),
        )
        
        return session
    
    async def _remove_session(self, session: Session) -> None:
        """Remove a session from the pool.
        
        Args:
            session: Session to remove
        """
        async with self._lock:
            if session.session_id in self._all_sessions:
                del self._all_sessions[session.session_id]
            
            if session in self._active_sessions:
                self._active_sessions.remove(session)
        
        # Terminate session
        await session.terminate()
        
        self._metrics.sessions_removed += 1
        
        logger.info(
            "Removed session",
            session_id=session.session_id,
            total_sessions=len(self._all_sessions),
        )
    
    async def _recycle_session(self, session: Session) -> None:
        """Recycle a session by restarting it.
        
        Args:
            session: Session to recycle
        """
        try:
            await session.restart()
            
            # Return to idle pool
            await self._idle_sessions.put(session)
            
            self._metrics.sessions_recycled += 1
            
            logger.info(
                "Recycled session",
                session_id=session.session_id,
            )
            
        except Exception as e:
            logger.error(
                "Failed to recycle session",
                session_id=session.session_id,
                error=str(e),
            )
            await self._remove_session(session)
    
    async def ensure_min_sessions(self) -> None:
        """Ensure minimum number of idle sessions are available."""
        tasks = []
        
        async with self._lock:
            current_idle = self._idle_sessions.qsize()
            current_total = len(self._all_sessions)
            
            # Calculate how many sessions we need
            needed = self._config.min_idle - current_idle
            
            # Don't exceed max sessions
            available_slots = self._config.max_sessions - current_total
            needed = min(needed, available_slots)
            
            if needed > 0:
                logger.debug(
                    "Pre-warming sessions",
                    needed=needed,
                    current_idle=current_idle,
                    current_total=current_total,
                )
                
                # Create tasks without holding lock
                for _ in range(needed):
                    task = asyncio.create_task(self._create_and_add_session())
                    tasks.append(task)
        
        # Wait for all sessions to be created
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    logger.error("Failed to pre-warm session", error=str(result))
    
    async def _create_and_add_session(self) -> None:
        """Create a session and add it to the idle pool."""
        try:
            session = await self._create_session()
            await self._idle_sessions.put(session)
        except Exception as e:
            logger.error("Failed to create session", error=str(e))
            raise
    
    async def _warmup_loop(self) -> None:
        """Background task to maintain minimum idle sessions."""
        while not self._shutdown:
            try:
                await self.ensure_min_sessions()
                await asyncio.sleep(10.0)  # Check every 10 seconds
                
            except Exception as e:
                logger.error("Warmup loop error", error=str(e))
                await asyncio.sleep(10.0)
    
    async def _health_check_loop(self) -> None:
        """Background task to check session health."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self._config.health_check_interval)
                
                # Check idle sessions
                idle_sessions = []
                
                # Drain queue to check all sessions
                while not self._idle_sessions.empty():
                    try:
                        session = self._idle_sessions.get_nowait()
                        idle_sessions.append(session)
                    except asyncio.QueueEmpty:
                        break
                
                # Check each session and return healthy ones
                for session in idle_sessions:
                    if session.is_alive:
                        # Check idle timeout
                        idle_time = time.time() - session.info.last_used_at
                        
                        if idle_time > self._config.session_timeout:
                            logger.info(
                                "Removing idle session",
                                session_id=session.session_id,
                                idle_time=idle_time,
                            )
                            await self._remove_session(session)
                        else:
                            await self._idle_sessions.put(session)
                    else:
                        logger.warning(
                            "Removing dead session",
                            session_id=session.session_id,
                        )
                        await self._remove_session(session)
                
            except Exception as e:
                logger.error("Health check error", error=str(e))
    
    def get_metrics(self) -> PoolMetrics:
        """Get pool metrics.
        
        Returns:
            Pool metrics
        """
        self._metrics.idle_sessions = self._idle_sessions.qsize()
        self._metrics.active_sessions = len(self._active_sessions)
        self._metrics.total_sessions = len(self._all_sessions)
        
        # Calculate hit rate
        total = self._metrics.pool_hits + self._metrics.pool_misses
        if total > 0:
            self._metrics.hit_rate = self._metrics.pool_hits / total
        
        # Calculate average acquisition time
        if self._metrics.acquisition_success > 0:
            self._metrics.avg_acquisition_time = (
                self._metrics.total_acquisition_time / self._metrics.acquisition_success
            )
        
        return self._metrics
    
    def get_info(self) -> Dict[str, Any]:
        """Get pool information.
        
        Returns:
            Pool status information
        """
        metrics = self.get_metrics()
        
        return {
            "config": {
                "min_idle": self._config.min_idle,
                "max_sessions": self._config.max_sessions,
                "session_timeout": self._config.session_timeout,
            },
            "status": {
                "idle_sessions": metrics.idle_sessions,
                "active_sessions": metrics.active_sessions,
                "total_sessions": metrics.total_sessions,
            },
            "metrics": {
                "hit_rate": metrics.hit_rate,
                "avg_acquisition_time": metrics.avg_acquisition_time,
                "sessions_created": metrics.sessions_created,
                "sessions_removed": metrics.sessions_removed,
                "sessions_recycled": metrics.sessions_recycled,
                "sessions_restarted": metrics.sessions_restarted,
                "acquisition_timeouts": metrics.acquisition_timeouts,
            },
        }


@dataclass
class PoolMetrics:
    """Metrics for session pool."""
    
    idle_sessions: int = 0
    active_sessions: int = 0
    total_sessions: int = 0
    sessions_created: int = 0
    sessions_removed: int = 0
    sessions_recycled: int = 0
    sessions_restarted: int = 0
    pool_hits: int = 0
    pool_misses: int = 0
    hit_rate: float = 0.0
    acquisition_attempts: int = 0
    acquisition_success: int = 0
    acquisition_timeouts: int = 0
    total_acquisition_time: float = 0.0
    avg_acquisition_time: float = 0.0