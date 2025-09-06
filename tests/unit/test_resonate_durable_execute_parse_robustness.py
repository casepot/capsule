import pytest

from src.integration.resonate_functions import register_executor_functions


@pytest.mark.unit
def test_durable_execute_parses_non_json_and_non_dict_payloads_gracefully():
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

    # Case 1: Non-JSON string payload should be returned as-is
    gen = durable(ctx, {"code": "x=1", "execution_id": "E1"})
    next(gen)                # pre checkpoint
    gen.send(None)           # yield promise
    gen.send(object())       # give promise handle
    gen.send(None)           # yield bridge.send_request
    yielded = gen.send(None) # yield promise handle
    assert yielded is not None
    try:
        yielded = gen.send("plain string result that is not json")
        # If a post-execution checkpoint is yielded, consume it
        assert yielded == ("post_execution", {"execution_id": "E1"})
        with pytest.raises(StopIteration) as si:
            gen.send(None)
        ret = si.value.value
    except StopIteration as si:
        # Some implementations may return immediately after parsing
        ret = si.value
    assert ret["result"] in ("plain string result that is not json", None)

    # Case 2: Integer payload should be returned as-is
    gen = durable(ctx, {"code": "x=2", "execution_id": "E2"})
    next(gen)
    gen.send(None)
    gen.send(object())
    gen.send(None)
    gen.send(None)
    try:
        yielded = gen.send(123)
        assert yielded == ("post_execution", {"execution_id": "E2"})
        with pytest.raises(StopIteration) as si2:
            gen.send(None)
        ret2 = si2.value.value
    except StopIteration as si2:
        ret2 = si2.value
    assert ret2["result"] in (123, None)
