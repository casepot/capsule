"""Pytest configuration and shared fixtures for PyREPL3 test suite."""

import asyncio
import pytest
import sys
import logging
from pathlib import Path
from typing import AsyncGenerator, Generator

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session.manager import Session
from src.session.config import SessionConfig
from src.session.pool import SessionPool, PoolConfig


# Configure logging for tests
logging.basicConfig(level=logging.WARNING)


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def session() -> AsyncGenerator[Session, None]:
    """Create a test session that's properly cleaned up."""
    session = Session(config=SessionConfig(
        startup_timeout=5.0,
        execute_timeout=5.0,
        shutdown_timeout=2.0,
    ))
    await session.start()
    yield session
    await session.shutdown()


@pytest.fixture
async def pool() -> AsyncGenerator[SessionPool, None]:
    """Create a test session pool that's properly cleaned up."""
    pool = SessionPool(config=PoolConfig(
        min_idle=1,
        max_sessions=3,
        warmup_code=None,
    ))
    await pool.start()
    yield pool
    await pool.shutdown()


@pytest.fixture
def warmup_code() -> str:
    """Sample warmup code for testing."""
    return """
import sys
print(f"Python {sys.version}")
x = 42
"""


@pytest.fixture
def test_code() -> dict[str, str]:
    """Collection of test code snippets."""
    return {
        "simple": "2 + 2",
        "print": "print('Hello, World!')",
        "error": "1/0",
        "infinite_loop": "while True: pass",
        "input": "name = input('Name: ')",
        "multiline": """
x = 10
y = 20
print(f"Sum: {x + y}")
""",
        "async": """
import asyncio
await asyncio.sleep(0.1)
print("Done")
""",
        "namespace": """
x = 100
print(f"x = {x}")
""",
    }


# Test markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Fast unit tests")
    config.addinivalue_line("markers", "integration: Component integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Tests that take >1s")
    config.addinivalue_line("markers", "stress: Performance/stress tests")
    config.addinivalue_line("markers", "regression: Regression tests for fixed bugs")
    config.addinivalue_line("markers", "skip_ci: Skip in CI environments")


# Timeout configuration
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add timeout based on markers."""
    for item in items:
        # Add timeout marker based on test type
        if item.get_closest_marker("slow"):
            item.add_marker(pytest.mark.timeout(30))
        elif item.get_closest_marker("stress"):
            item.add_marker(pytest.mark.timeout(60))
        elif item.get_closest_marker("unit"):
            item.add_marker(pytest.mark.timeout(5))
        else:
            item.add_marker(pytest.mark.timeout(10))