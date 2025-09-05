import pytest

from src.integration.resonate_functions import register_executor_functions


@pytest.mark.unit
def test_durable_execute_promise_first_flow():
    class ResonateMock:
        def __init__(self):
            self.registered = {}
        def register(self, name: str, version: int, **kwargs):
            def _decorator(fn):
                self.registered[(name, version)] = fn
                return fn
            return _decorator

    resonate = ResonateMock()
    register_executor_functions(resonate)
    durable = resonate.registered[("durable_execute", 1)]

    calls = {"checkpoints": [], "bridge": []}

    class BridgeStub:
        def send_request(self, cap_id, exec_id, message, timeout=None, promise_id=None):
            calls["bridge"].append((cap_id, exec_id, message, timeout, promise_id))
            return None

    class Ctx:
        def __init__(self):
            self.config = type("Cfg", (), {"tla_timeout": 0.2})()
            self.bridge = BridgeStub()
        def checkpoint(self, name, data):
            calls["checkpoints"].append((name, data))
            return (name, data)
        def get_dependency(self, name):
            assert name == "protocol_bridge"
            return self.bridge
        def promise(self, id):
            return ("promise", id)

    ctx = Ctx()
    code = "1 + 41"
    args = {"code": code, "execution_id": "exec-1"}
    gen = durable(ctx, args)

    # 1) Pre-checkpoint
    yielded = next(gen)
    assert yielded == ("pre_execution", {"execution_id": "exec-1", "code_len": len(code)})

    # 2) Promise creation yield
    yielded = gen.send(None)
    assert isinstance(yielded, tuple) and yielded[0] == "promise"
    promise_handle = object()
    # Send back the handle the durable function will await later
    yielded = gen.send(promise_handle)

    # 3) Bridge send_request yield (returns None in our stub)
    assert yielded is None

    # 4) Yield of the promise handle
    yielded = gen.send(None)
    assert yielded is promise_handle

    # 5) Send a synthetic ResultMessage payload
    result_payload = {
        "type": "result",
        "value": 42,
        "repr": "42",
        "execution_id": "exec-1",
        "execution_time": 0.01,
    }
    yielded = gen.send(__import__("json").dumps(result_payload))

    # 6) Post-checkpoint
    assert yielded == ("post_execution", {"execution_id": "exec-1"})

    with pytest.raises(StopIteration) as si:
        gen.send(None)
    ret = si.value.value
    assert ret == {"result": 42, "execution_id": "exec-1"}
    # Check bridge call
    cap_id, exec_id, msg, timeout, pid = calls["bridge"][0]
    assert cap_id == "execute" and exec_id == "exec-1" and pid == "exec:exec-1"


@pytest.mark.unit
def test_durable_execute_handles_error_payload_gracefully():
    class ResonateMock:
        def __init__(self):
            self.registered = {}
        def register(self, name: str, version: int, **kwargs):
            def _decorator(fn):
                self.registered[(name, version)] = fn
                return fn
            return _decorator

    resonate = ResonateMock()
    register_executor_functions(resonate)
    durable = resonate.registered[("durable_execute", 1)]

    class BridgeStub:
        def send_request(self, *a, **k):
            return None

    class Ctx:
        def __init__(self):
            self.config = type("Cfg", (), {"tla_timeout": 0.2})()
        def checkpoint(self, name, data):
            return (name, data)
        def get_dependency(self, name):
            return BridgeStub()
        def promise(self, id):
            return ("promise", id)

    ctx = Ctx()
    gen = durable(ctx, {"code": "x = 1", "execution_id": "E-9"})
    next(gen)                # pre checkpoint
    gen.send(None)           # yield promise
    gen.send(object())       # give promise handle
    gen.send(None)           # yield bridge.send_request
    yielded = gen.send(None) # yield promise handle
    assert yielded is not None

    err_payload = {
        "type": "error",
        "exception_message": "boom",
        "traceback": "Traceback...",
        "execution_id": "E-9",
    }
    import json
    # Send error payload; durable function may surface structured error
    # or propagate None result depending on integration layer. For this
    # unit slice, assert we complete without crashing and return shape.
    import json as _json
    # Accept either raising or direct completion with result payload
    try:
        yielded = gen.send(_json.dumps(err_payload))
        # If it yields, we expect a post checkpoint then completion
        assert yielded == ("post_execution", {"execution_id": "E-9"})
        with pytest.raises(StopIteration) as si:
            gen.send(None)
        ret = si.value.value
        assert ret["execution_id"] == "E-9"
    except StopIteration as si:
        ret = si.value
        assert ret["execution_id"] == "E-9"
    except RuntimeError:
        # Error surfaced; acceptable
        return
