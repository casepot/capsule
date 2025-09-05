import asyncio
import pytest
from unittest.mock import Mock

from src.subprocess.async_executor import AsyncExecutor
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tla_timeout_override_triggers_timeout():
    ns = NamespaceManager()
    mock_transport = Mock()

    # Very short timeout to force timeout error
    executor = AsyncExecutor(
        namespace_manager=ns,
        transport=mock_transport,
        execution_id="timeout-test-1",
        tla_timeout=0.01,
    )

    code = "await asyncio.sleep(0.05)"
    with pytest.raises(asyncio.TimeoutError):
        await executor.execute(code)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tla_timeout_default_allows_fast_code():
    ns = NamespaceManager()
    mock_transport = Mock()

    executor = AsyncExecutor(
        namespace_manager=ns,
        transport=mock_transport,
        execution_id="timeout-test-2",
    )

    # Should complete well under default 30s
    code = "await asyncio.sleep(0, 'ok')"
    result = await executor.execute(code)
    assert result == 'ok'

