#!/usr/bin/env python3
"""Capsule - Advanced Python REPL with subprocess isolation."""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

import structlog

from src.protocol.messages import ExecuteMessage, MessageType
from src.session.manager import Session
from src.session.pool import PoolConfig, SessionPool

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


async def demo_single_session() -> None:
    """Demonstrate single session usage."""
    print("=== Single Session Demo ===\n")
    
    # Create and start a session
    session = Session()
    await session.start()
    
    try:
        # Execute some code
        code = """
import sys
print(f"Python version: {sys.version}")
print("Hello from subprocess!")

def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(5)
print(f"5! = {result}")
result
"""
        
        print(f"Executing code in session {session.session_id}...")
        print("-" * 40)
        
        # Create execute message
        message = ExecuteMessage(
            id="exec-1",
            timestamp=0,
            code=code,
        )
        
        # Execute and collect output
        async for msg in session.execute(message):
            if msg.type == MessageType.OUTPUT:
                print(msg.data, end="")  # type: ignore
            elif msg.type == MessageType.RESULT:
                print(f"\nResult: {msg.repr}")  # type: ignore
            elif msg.type == MessageType.ERROR:
                print(f"\nError: {msg.traceback}")  # type: ignore
        
        print("-" * 40)
        
    finally:
        await session.shutdown()


async def demo_session_pool() -> None:
    """Demonstrate session pool usage."""
    print("\n=== Session Pool Demo ===\n")
    
    # Configure pool
    config = PoolConfig(
        min_idle=2,
        max_sessions=5,
        warmup_code="import math\nimport json\n",
    )
    
    # Create and start pool
    pool = SessionPool(config)
    await pool.start()
    
    try:
        # Acquire sessions and execute code
        tasks = []
        
        for i in range(3):
            async def execute_task(task_id: int) -> None:
                # Acquire session
                session = await pool.acquire()
                
                try:
                    code = f"""
import time
print(f"Task {task_id} running in session {{__name__}}")
time.sleep(0.1)
result = {task_id} ** 2
print(f"Task {task_id} result: {{result}}")
result
"""
                    
                    message = ExecuteMessage(
                        id=f"exec-{task_id}",
                        timestamp=0,
                        code=code,
                    )
                    
                    async for msg in session.execute(message):
                        if msg.type == MessageType.OUTPUT:
                            print(f"[Task {task_id}] {msg.data}", end="")  # type: ignore
                        elif msg.type == MessageType.RESULT:
                            print(f"[Task {task_id}] Result: {msg.repr}")  # type: ignore
                    
                finally:
                    # Release session back to pool
                    await pool.release(session)
            
            tasks.append(execute_task(i))
        
        # Run tasks concurrently
        await asyncio.gather(*tasks)
        
        # Print pool metrics
        print("\n" + "=" * 40)
        print("Pool Metrics:")
        info = pool.get_info()
        print(f"  Idle sessions: {info['status']['idle_sessions']}")
        print(f"  Active sessions: {info['status']['active_sessions']}")
        print(f"  Total sessions: {info['status']['total_sessions']}")
        print(f"  Hit rate: {info['metrics']['hit_rate']:.2%}")
        
    finally:
        await pool.stop()


async def demo_transactions() -> None:
    """Demonstrate transaction support."""
    print("\n=== Transaction Demo ===\n")
    
    from src.subprocess.namespace import NamespaceManager
    from src.protocol.messages import TransactionPolicy
    
    namespace_mgr = NamespaceManager()
    
    # Execute with rollback on failure
    print("Testing rollback on failure...")
    namespace_mgr.execute("x = 10")
    print(f"x = {namespace_mgr.namespace.get('x')}")
    
    try:
        namespace_mgr.execute(
            "x = 20\nraise ValueError('Test error')",
            transaction_id="txn1",
            policy=TransactionPolicy.ROLLBACK_ON_FAILURE,
        )
    except ValueError:
        print("Error occurred, checking rollback...")
    
    print(f"x = {namespace_mgr.namespace.get('x')} (should still be 10)")
    
    # Execute with always rollback
    print("\nTesting always rollback...")
    result = namespace_mgr.execute(
        "y = 100\ny * 2",
        transaction_id="txn2",
        policy=TransactionPolicy.ROLLBACK_ALWAYS,
    )
    print(f"Result: {result}")
    print(f"y exists: {'y' in namespace_mgr.namespace} (should be False)")


async def main() -> None:
    """Main entry point."""
    print("Capsule - Advanced Python REPL System")
    print("=" * 40)
    
    try:
        # Run demos
        await demo_single_session()
        await demo_session_pool()
        await demo_transactions()
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        logger.error("Demo error", error=str(e), exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())