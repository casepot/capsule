"""Session-related test fixtures."""

import asyncio
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from src.session.manager import Session
from src.session.config import SessionConfig
from src.session.pool import SessionPool, PoolConfig


@asynccontextmanager
async def create_session(
    warmup_code: str | None = None,
    startup_timeout: float = 5.0,
    execute_timeout: float = 5.0,
) -> AsyncGenerator[Session, None]:
    """Create a session with automatic cleanup."""
    config = SessionConfig(
        warmup_code=warmup_code,
        startup_timeout=startup_timeout,
        execute_timeout=execute_timeout,
        shutdown_timeout=2.0,
    )
    session = Session(config=config)
    try:
        await session.start()
        yield session
    finally:
        await session.shutdown()


@asynccontextmanager
async def create_pool(
    min_idle: int = 1,
    max_sessions: int = 3,
    warmup_code: str | None = None,
) -> AsyncGenerator[SessionPool, None]:
    """Create a session pool with automatic cleanup."""
    config = PoolConfig(
        min_idle=min_idle,
        max_sessions=max_sessions,
        warmup_code=warmup_code,
    )
    pool = SessionPool(config=config)
    try:
        await pool.start()
        yield pool
    finally:
        await pool.shutdown()


class SessionHelper:
    """Helper class for session testing."""
    
    @staticmethod
    async def execute_code(session: Session, code: str) -> list:
        """Execute code and collect all messages."""
        from src.protocol.messages import ExecuteMessage
        import time
        
        msg = ExecuteMessage(
            id=f"test-{time.time()}",
            timestamp=time.time(),
            code=code,
        )
        
        messages = []
        async for response in session.execute(msg):
            messages.append(response)
        return messages
    
    @staticmethod
    async def execute_with_timeout(
        session: Session, 
        code: str, 
        timeout: float = 5.0
    ) -> list:
        """Execute code with a timeout."""
        from src.protocol.messages import ExecuteMessage
        import time
        
        msg = ExecuteMessage(
            id=f"test-{time.time()}",
            timestamp=time.time(),
            code=code,
        )
        
        messages = []
        try:
            async with asyncio.timeout(timeout):
                async for response in session.execute(msg):
                    messages.append(response)
        except asyncio.TimeoutError:
            pass
        return messages