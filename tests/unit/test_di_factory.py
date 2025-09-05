import pytest

from src.integration.resonate_wrapper import async_executor_factory
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
def test_factory_timeout_from_ctx_config():
    # Arrange
    class Ctx:
        def __init__(self):
            self.config = type("Cfg", (), {"tla_timeout": 0.2})()
            self.execution_id = "X-1"

    ctx = Ctx()
    ns = NamespaceManager()

    # Act
    exec1 = async_executor_factory(ctx=ctx, namespace_manager=ns, transport=None)

    # Assert
    assert exec1.tla_timeout == pytest.approx(0.2)


@pytest.mark.unit
def test_new_executor_per_execution():
    class Ctx:
        def __init__(self, eid):
            self.config = type("Cfg", (), {"tla_timeout": 0.3})()
            self.execution_id = eid

    ns = NamespaceManager()
    ctx1 = Ctx("A")
    ctx2 = Ctx("B")

    e1 = async_executor_factory(ctx=ctx1, namespace_manager=ns, transport=None)
    e2 = async_executor_factory(ctx=ctx2, namespace_manager=ns, transport=None)

    assert e1 is not e2
    assert e1.execution_id == "A"
    assert e2.execution_id == "B"

