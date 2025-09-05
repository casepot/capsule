import pytest
from unittest.mock import Mock

from src.integration.resonate_functions import register_executor_functions


@pytest.mark.unit
def test_durable_execute_routes_tla_and_checkpoints():
    # Arrange resonate mock storing decorator registration
    class ResonateMock:
        def __init__(self):
            self.registered = {}

        def register(self, name: str, version: str, **kwargs):
            def _decorator(fn):
                self.registered[(name, version)] = fn
                return fn

            return _decorator

    resonate = ResonateMock()
    register_executor_functions(resonate)
    durable = resonate.registered[("durable_execute", 1)]

    # Fake ctx: supports checkpoint, lfc, get_dependency, config
    calls = {"checkpoints": []}

    class Ctx:
        def __init__(self):
            self.config = type("Cfg", (), {"tla_timeout": 0.2})()

        def checkpoint(self, name, data):
            calls["checkpoints"].append((name, data))
            return (name, data)

        def get_dependency(self, name):
            assert name == "async_executor"

            def factory(_ctx):
                # Executor stub with execute callable invoked via ctx.lfc
                class Exec:
                    def execute(self, code: str):
                        return 42

                return Exec()

            return factory

        def lfc(self, fn, args):
            # Durable function should yield this, and test will send result back
            assert "code" in args
            return (fn, args)

    ctx = Ctx()
    code = "await asyncio.sleep(0); 1 + 41"  # TLA-like code
    args = {"code": code, "execution_id": "exec-1"}

    # Act: drive the generator manually to simulate Resonate scheduler
    gen = durable(ctx, args)

    # First yield: pre-execution checkpoint
    yielded = next(gen)
    assert yielded == ("pre_execution", {"execution_id": "exec-1", "code_len": len(code)})

    # Second yield: lfc of executor.execute
    yielded = gen.send(None)
    fn, fn_args = yielded
    # Simulate await of fn(**fn_args)
    # Send synthetic result back as if lfc awaited it
    yielded = gen.send(42)

    # Third yield: post-execution checkpoint
    assert yielded == ("post_execution", {"execution_id": "exec-1"})

    # Finish and capture return value
    with pytest.raises(StopIteration) as si:
        gen.send(None)
    ret = si.value.value
    assert ret == {"result": 42, "execution_id": "exec-1"}
    # Check both checkpoints recorded
    assert calls["checkpoints"][0][0] == "pre_execution"
    assert calls["checkpoints"][1][0] == "post_execution"


@pytest.mark.unit
def test_durable_execute_rejects_active_event_loop(monkeypatch):
    """Ensure the lfc wrapper raises when a loop is already running (no loop spinning)."""
    class ResonateMock:
        def __init__(self):
            self.registered = {}
        def register(self, name: str, version: int, **kwargs):
            def _decorator(fn):
                self.registered[(name, version)] = fn
                return fn
            return _decorator

    resonate = ResonateMock()
    durable = register_executor_functions(resonate)
    durable = resonate.registered[("durable_execute", 1)]

    class Ctx:
        def checkpoint(self, name, data):
            return (name, data)
        def get_dependency(self, name):
            assert name == "async_executor"
            def factory(_ctx):
                class Exec:
                    async def execute(self, code: str):
                        return 42
                return Exec()
            return factory
        # lfc calls the provided callable synchronously
        def lfc(self, fn, args):
            return fn(self, args)

    # Make asyncio.get_running_loop return a dummy loop (simulate active loop)
    import asyncio as _asyncio
    monkeypatch.setattr(_asyncio, "get_running_loop", lambda: object())

    gen = durable(Ctx(), {"code": "1+2", "execution_id": "X"})
    next(gen)  # pre checkpoint
    with pytest.raises(RuntimeError, match="lfc wrapper cannot run inside an active event loop"):
        # Trigger the lfc call which should raise from inside durable function
        next(gen)

def test_durable_execute_error_adds_notes():
    class ResonateMock:
        def __init__(self):
            self.registered = {}

        def register(self, name: str, version: str, **kwargs):
            def _decorator(fn):
                self.registered[(name, version)] = fn
                return fn

            return _decorator

    resonate = ResonateMock()
    register_executor_functions(resonate)
    durable = resonate.registered[("durable_execute", 1)]

    class Ctx:
        def checkpoint(self, name, data):
            return (name, data)

        def get_dependency(self, name):
            def factory(_ctx):
                class Exec:
                    async def execute(self, code: str):  # pragma: no cover - not called
                        return None

                return Exec()

            return factory

        def lfc(self, fn, args):
            return (fn, args)

    ctx = Ctx()
    code = "print('x')"
    args = {"code": code, "execution_id": "E-9"}
    gen = durable(ctx, args)

    next(gen)  # pre checkpoint
    _ = gen.send(None)  # lfc yielded

    # Throw error into generator at lfc yield point
    err = Exception("boom")
    with pytest.raises(Exception) as ex:
        gen.throw(err)
    e = ex.value
    # Python 3.11+ exceptions have __notes__
    notes = getattr(e, "__notes__", [])
    assert any("Execution ID: E-9" in n for n in notes)
    assert any(f"Code length: {len(code)}" in n for n in notes)
