import pytest

from types import SimpleNamespace

from src.integration.resonate_wrapper import async_executor_factory
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
def test_factory_passes_detection_and_cache_knobs():
    ns = NamespaceManager()

    class Cfg(SimpleNamespace):
        pass

    cfg = Cfg(
        tla_timeout=12.5,
        ast_cache_max_size=2,
        blocking_modules={"time", "os"},
        blocking_methods_by_module={"time": {"sleep"}},
        warn_on_blocking=False,
    )
    ctx = SimpleNamespace(config=cfg, execution_id="di-knobs")

    ex = async_executor_factory(
        ctx=ctx,
        namespace_manager=ns,
        transport=None,
    )

    # Timeout applied
    assert ex.tla_timeout == 12.5
    # Cache size applied
    assert ex._ast_cache_max_size == 2
    # Policy merged/applied
    assert "time" in ex._policy.blocking_modules
    assert "sleep" in ex._policy.blocking_methods_by_module.get("time", set())

