import pytest

from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
def test_namespace_manager_compile_flags_eval_exec():
    ns = NamespaceManager()
    # Eval simple expression
    result = ns.execute("1 + 1")
    assert result == 2
    # Exec statements; ensure no exception and state updated
    result2 = ns.execute("x = 3\ny = x + 4")
    assert result2 is None
    assert ns.namespace.get("x") == 3
    assert ns.namespace.get("y") == 7

