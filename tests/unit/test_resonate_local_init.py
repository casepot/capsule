import pytest
from unittest.mock import AsyncMock, Mock

from src.integration.resonate_init import initialize_resonate_local
from src.integration.resonate_functions import register_executor_functions
from src.integration.resonate_bridge import ResonateProtocolBridge
from src.integration.capability_input import InputCapability


@pytest.mark.unit
def test_resonate_local_registers_and_runs_durable_execute():
    # Require real SDK import
    from resonate import Resonate  # type: ignore

    transport = AsyncMock()
    res = Resonate.local()
    # Wire DI and function registration on this instance
    initialize_resonate_local(transport, resonate=res)
    # Grab decorated function handle attached by registration
    durable = getattr(res, "capsule_durable_execute", None)
    assert durable is not None

    # Run simple code path and assert result is returned
    # Prefer Resonate.run to get direct result with current SDK
    result = durable.run("exec-rt-1b", {"code": "1+2", "execution_id": "exec-rt-1b"})
    assert isinstance(result, dict)
    assert result.get("result") == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resonate_local_input_flow_integration():
    from resonate import Resonate  # type: ignore

    transport = AsyncMock()
    resonate = Resonate.local()
    initialize_resonate_local(transport, resonate=resonate)

    # Access bridge via DI from provider closure in init (not public API).
    # We re-register durable functions on the same instance for isolation.
    bridge = ResonateProtocolBridge(resonate, transport)  # local bridge for test

    # Patch bridge to return a resolved promise-like object
    class Promise:
        async def result(self):
            return '{"input": "world"}'

    async def fake_send_request(cap_id, exec_id, message, timeout=None):
        # Verify basic shape
        assert cap_id == "input"
        assert exec_id == "E2E"
        assert hasattr(message, "prompt")
        return Promise()

    bridge.send_request = fake_send_request  # type: ignore

    cap = InputCapability(resonate, transport, bridge)
    out = await cap.request_input("hello?", execution_id="E2E")
    assert out == "world"


@pytest.mark.unit
def test_resonate_local_dependencies_and_executor_factory():
    from resonate import Resonate  # type: ignore
    from src.subprocess.async_executor import AsyncExecutor

    transport = AsyncMock()
    res = Resonate.local()
    initialize_resonate_local(transport, resonate=res)

    # Probe dependencies via durable context (ctx.get_dependency)
    @res.register(name="probe_deps", version=1)
    def probe(ctx, args):
        bridge = ctx.get_dependency("protocol_bridge")
        ns = ctx.get_dependency("namespace_manager")
        cap1 = ctx.get_dependency("input_capability")()
        cap2 = ctx.get_dependency("input_capability")()
        exec_factory = ctx.get_dependency("async_executor")
        e1 = exec_factory(ctx)
        e2 = exec_factory(ctx)
        return {
            "bridge_is_bridge": isinstance(bridge, ResonateProtocolBridge),
            "ns_exists": ns is not None,
            "caps_new_instances": cap1 is not cap2 and isinstance(cap1, InputCapability),
            "execs_new_instances": (e1 is not e2) and isinstance(e1, AsyncExecutor),
            "exec_id": getattr(e1, "execution_id", None),
        }

    result = probe.run("probe-1", {})
    assert result["bridge_is_bridge"] is True
    assert result["ns_exists"] is True
    assert result["caps_new_instances"] is True
    assert result["execs_new_instances"] is True
    # Default exec_id fallback if ctx lacks execution_id attribute
    assert result["exec_id"] == "local-exec"
