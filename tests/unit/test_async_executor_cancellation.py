"""Unit tests for AsyncExecutor cooperative cancellation and lifecycle.

Validates that only the top-level coroutine created by the executor is cancelled,
that cancellation is prompt, notes are attached, telemetry counters update, and
no coroutine leaks remain after execution.
"""

import asyncio
import time
import pytest
import threading

from src.subprocess.async_executor import AsyncExecutor
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
class TestAsyncCancellation:
    @pytest.mark.asyncio
    async def test_tla_cancellation_is_prompt_and_cleans_up(self):
        ns = NamespaceManager()
        ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="cancel-tla-1")

        # Start a long await under TLA
        task = asyncio.create_task(ex.execute("await asyncio.sleep(10)"))

        await asyncio.sleep(0.01)
        t0 = time.perf_counter()
        effective = ex.cancel_current(reason="user_request")
        assert effective is True

        with pytest.raises(asyncio.CancelledError) as exc:
            await task

        dt = time.perf_counter() - t0
        assert dt < 0.1, f"Cancellation took {dt:.3f}s, expected <100ms"

        # Verify notes present
        notes = getattr(exc.value, "__notes__", [])
        assert any("execution_id=cancel-tla-1" in n for n in notes)
        assert any("cancel_reason=user_request" in n for n in notes)

        # Telemetry: requested/effective incremented; errors unchanged; cancelled_errors incremented
        assert ex.stats["cancels_requested"] == 1
        assert ex.stats["cancels_effective"] == 1
        assert ex.stats["errors"] == 0
        assert ex.stats["cancelled_errors"] == 1

        # No coroutine leaks
        assert ex.cleanup_coroutines() == 0

    @pytest.mark.asyncio
    async def test_ast_fallback_cancellation(self, monkeypatch):
        ns = NamespaceManager()
        ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="cancel-ast-1")

        # Force TLA compile paths to fail to trigger AST fallback
        import builtins as _builtins
        orig_compile = _builtins.compile

        def fake_compile(source, filename, mode, flags=0, dont_inherit=False, optimize=-1):
            from src.subprocess.async_executor import AsyncExecutor as _AE
            if flags & _AE.PyCF_ALLOW_TOP_LEVEL_AWAIT:
                raise SyntaxError("force fallback")
            return orig_compile(source, filename, mode, flags=flags, dont_inherit=dont_inherit, optimize=optimize)

        import src.subprocess.async_executor as ae_mod
        monkeypatch.setattr(ae_mod, "compile", fake_compile, raising=False)

        task = asyncio.create_task(ex.execute("await asyncio.sleep(10)"))
        await asyncio.sleep(0.01)
        t0 = time.perf_counter()
        ok = ex.cancel_current(reason="ast_fallback_cancel")
        assert ok is True

        with pytest.raises(asyncio.CancelledError) as exc:
            await task

        dt = time.perf_counter() - t0
        assert dt < 0.1, f"Cancellation took {dt:.3f}s, expected <100ms"
        notes = getattr(exc.value, "__notes__", [])
        assert any("execution_id=cancel-ast-1" in n for n in notes)
        assert any("cancel_reason=ast_fallback_cancel" in n for n in notes)

        # Telemetry: cancelled_errors incremented
        assert ex.stats["cancelled_errors"] == 1

        # No leaks
        assert ex.cleanup_coroutines() == 0

    @pytest.mark.asyncio
    async def test_cancel_noop_when_idle(self):
        ns = NamespaceManager()
        ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="cancel-noop-1")

        ok = ex.cancel_current(reason="noop")
        assert ok is False
        assert ex.stats["cancels_requested"] == 1
        assert ex.stats["cancels_noop"] == 1
        assert ex.stats["cancels_effective"] == 0

    @pytest.mark.asyncio
    async def test_does_not_cancel_user_tasks(self):
        ns = NamespaceManager()
        ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="cancel-user-1")

        # Create background user task first (simple sync path so it persists in namespace)
        await ex.execute("import asyncio; bg = asyncio.create_task(asyncio.sleep(1))")
        # Now run a separate long await as top-level and cancel it
        run_task = asyncio.create_task(ex.execute("await asyncio.sleep(10)"))
        await asyncio.sleep(0.01)
        ex.cancel_current(reason="only_top_level")
        with pytest.raises(asyncio.CancelledError):
            await run_task

        # Background task should still be present and not necessarily cancelled
        bg = ns.namespace.get("bg")
        assert bg is not None
        assert isinstance(bg, asyncio.Task)
        assert not bg.cancelled()

        # Cleanup background task to avoid leaks in tests
        try:
            await asyncio.wait_for(bg, timeout=1.0)
        except asyncio.TimeoutError:
            bg.cancel()
            with pytest.raises(asyncio.CancelledError):
                await bg
        except asyncio.CancelledError:
            pass

        assert ex.cleanup_coroutines() == 0

    @pytest.mark.asyncio
    async def test_multiple_background_tasks_untouched(self):
        ns = NamespaceManager()
        ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="cancel-user-many")

        # Create multiple background tasks
        await ex.execute(
            "import asyncio; bg1 = asyncio.create_task(asyncio.sleep(1)); bg2 = asyncio.create_task(asyncio.sleep(1))"
        )
        # Start a long-running top-level await and cancel it
        run_task = asyncio.create_task(ex.execute("await asyncio.sleep(10)"))
        await asyncio.sleep(0.01)
        ex.cancel_current(reason="only_top_level_many")
        with pytest.raises(asyncio.CancelledError):
            await run_task

        bg1 = ns.namespace.get("bg1")
        bg2 = ns.namespace.get("bg2")
        assert isinstance(bg1, asyncio.Task)
        assert isinstance(bg2, asyncio.Task)
        assert not bg1.cancelled()
        assert not bg2.cancelled()

        # Cleanup both background tasks
        for t in (bg1, bg2):
            try:
                await asyncio.wait_for(t, timeout=1.0)
            except asyncio.TimeoutError:
                t.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await t
            except asyncio.CancelledError:
                pass

        assert ex.cleanup_coroutines() == 0

    @pytest.mark.asyncio
    async def test_cleanup_on_error_still_works(self):
        ns = NamespaceManager()
        ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="cancel-err-1")

        code = """
async def boom():
    import asyncio
    await asyncio.sleep(0)
    raise NameError('boom')

await boom()
"""
        with pytest.raises(NameError):
            await ex.execute(code)

        # Ensure cleanup leaves no pending refs
        assert ex.cleanup_coroutines() == 0

    @pytest.mark.asyncio
    async def test_cross_thread_cancellation_is_thread_safe(self):
        ns = NamespaceManager()
        ex = AsyncExecutor(namespace_manager=ns, transport=None, execution_id="cancel-xthread-1")

        # Start a long-running top-level await
        task = asyncio.create_task(ex.execute("await asyncio.sleep(10)"))
        await asyncio.sleep(0.02)

        # Issue cancel from a different thread
        t0 = time.perf_counter()
        th = threading.Thread(target=lambda: ex.cancel_current(reason="xthread"))
        th.start()
        th.join(timeout=1.0)

        with pytest.raises(asyncio.CancelledError) as exc:
            await task

        latency = time.perf_counter() - t0
        assert latency < 0.6, f"Cross-thread cancellation latency {latency:.3f}s exceeds 600ms"

        # Notes include reason
        notes = getattr(exc.value, "__notes__", [])
        assert any("cancel_reason=xthread" in n for n in notes)

        # Telemetry
        assert ex.stats["cancels_requested"] >= 1
        assert ex.stats["cancels_effective"] >= 1
        assert ex.stats["cancelled_errors"] >= 1

        # No leaks
        assert ex.cleanup_coroutines() == 0
