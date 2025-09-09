"""Detection breadth and false-positive reduction tests for AsyncExecutor.

Covers:
- Overshadowing guards for names and attribute bases.
- Alias tracking and deep attribute chains.
- Telemetry counters and configurable policy knobs.
"""

import pytest

from src.subprocess.async_executor import AsyncExecutor, ExecutionMode
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
class TestBlockingIODetectionBreadth:
    def make_executor(self, **kwargs) -> AsyncExecutor:
        return AsyncExecutor(namespace_manager=NamespaceManager(), transport=None, execution_id="det-breadth", **kwargs)

    # ----------------- Overshadowing: should NOT detect blocking -----------------
    def test_overshadowing_simple_module_name(self):
        ex = self.make_executor()
        code = """
requests = object()
requests.get('http://example.com')
"""
        assert ex.analyze_execution_mode(code) == ExecutionMode.SIMPLE_SYNC

    def test_overshadowing_after_alias_import(self):
        ex = self.make_executor()
        code = """
import requests as rq
rq = object()
rq.get('http://example.com')
"""
        # Import of a blocking module is still considered blocking; overshadow prevents
        # call-based detection, but import-based detection remains.
        mode = ex.analyze_execution_mode(code)
        assert mode == ExecutionMode.BLOCKING_SYNC
        # Ensure overshadow guard recorded a skip
        assert ex.stats["overshadow_guard_skips"] >= 1

    def test_overshadowing_imported_function_alias(self):
        ex = self.make_executor()
        code = """
from requests import get as g
g = lambda *a, **k: None
g('http://example.com')
"""
        mode = ex.analyze_execution_mode(code)
        # Import presence yields blocking via import; overshadow prevents call classification
        assert mode == ExecutionMode.BLOCKING_SYNC
        assert ex.stats["overshadow_guard_skips"] >= 1

    def test_overshadowing_affects_deep_chain_base(self):
        ex = self.make_executor()
        code = """
socket = object()
socket.socket().recv(1)
"""
        assert ex.analyze_execution_mode(code) == ExecutionMode.SIMPLE_SYNC

    def test_overshadowing_custom_time_object(self):
        ex = self.make_executor()
        code = """
time = type('T', (), {'sleep': lambda *_: None})()
time.sleep(0.01)
"""
        assert ex.analyze_execution_mode(code) == ExecutionMode.SIMPLE_SYNC

    def test_warn_on_blocking_disables_logs(self, monkeypatch):
        # Ensure logger warnings/infos are not emitted when warn_on_blocking=False
        ex = AsyncExecutor(namespace_manager=NamespaceManager(), transport=None, execution_id="det-logs", warn_on_blocking=False)
        from src.subprocess import async_executor as ae_mod
        mocked_logger = type("L", (), {"warning": lambda *a, **k: (_ for _ in ()).throw(AssertionError("warning called")),
                                         "info": lambda *a, **k: (_ for _ in ()).throw(AssertionError("info called")),
                                         "debug": lambda *a, **k: None})()
        monkeypatch.setattr(ae_mod, "logger", mocked_logger, raising=True)
        # This includes both import and attribute call paths; neither should log when disabled
        code = """
import requests
requests.get('http://example.com')
"""
        # Should still detect BLOCKING_SYNC but not emit logs
        assert ex.analyze_execution_mode(code) == ExecutionMode.BLOCKING_SYNC

    # ----------------- Positive controls: should detect blocking -----------------
    def test_attribute_calls_on_blocking_modules(self):
        ex = self.make_executor()
        cases = [
            ("import requests\nrequests.get('http://example.com')", ExecutionMode.BLOCKING_SYNC),
            ("from requests import get\nget('http://example.com')", ExecutionMode.BLOCKING_SYNC),
            ("import socket\nsocket.socket().recv(1)", ExecutionMode.BLOCKING_SYNC),
            ("from socket import socket as sock\nsock().recv(1)", ExecutionMode.BLOCKING_SYNC),
            ("from urllib.request import urlopen\nurlopen('http://example.com')", ExecutionMode.BLOCKING_SYNC),
            ("import os\nos.system('true')", ExecutionMode.BLOCKING_SYNC),
            ("from pathlib import Path\nPath('f').read_text()", ExecutionMode.BLOCKING_SYNC),
        ]
        for code, expected in cases:
            assert ex.analyze_execution_mode(code) == expected

    # ----------------- Telemetry counters -----------------
    def test_counters_import_call_and_missed_chain(self):
        ex = self.make_executor()

        # Blocking import increments detected_blocking_import
        assert ex.analyze_execution_mode("import requests") == ExecutionMode.BLOCKING_SYNC
        assert ex.stats["detected_blocking_import"] >= 1

        # Blocking direct call increments detected_blocking_call
        before_calls = ex.stats["detected_blocking_call"]
        assert ex.analyze_execution_mode("import time\ntime.sleep(0)") == ExecutionMode.BLOCKING_SYNC
        assert ex.stats["detected_blocking_call"] == before_calls + 1

        # Missed chain increments missed_attribute_chain
        before_missed = ex.stats["missed_attribute_chain"]
        assert ex.analyze_execution_mode("(1+2).bit_length()") == ExecutionMode.SIMPLE_SYNC
        assert ex.stats["missed_attribute_chain"] == before_missed + 1

    # ----------------- Config toggles -----------------
    def test_require_import_for_module_calls_default(self):
        # With default require_import_for_module_calls=True, a bare name that matches a module
        # should not trigger blocking detection when not imported.
        ex = self.make_executor()
        assert ex.analyze_execution_mode("requests.get('http://x')") == ExecutionMode.SIMPLE_SYNC

    def test_override_blocking_methods(self):
        ex = self.make_executor(blocking_methods_by_module={"os": {"stat"}})
        assert ex.analyze_execution_mode("import os\nos.stat('x')") == ExecutionMode.BLOCKING_SYNC

    def test_require_import_for_module_calls_disabled(self):
        # When disabled, unimported module-looking attribute calls are treated as blocking
        ex = self.make_executor(require_import_for_module_calls=False)
        assert ex.analyze_execution_mode("requests.get('http://x')") == ExecutionMode.BLOCKING_SYNC

    # ----------------- Ordering: overshadow AFTER call does not suppress -----------------
    def test_overshadowing_after_call_still_detects_imported(self):
        ex = self.make_executor()
        cases = [
            ("import requests\nrequests.get('http://x')\nrequests = object()", ExecutionMode.BLOCKING_SYNC),
            ("import requests as rq\nrq.get('http://x')\nrq = object()", ExecutionMode.BLOCKING_SYNC),
            ("from requests import get as g\ng('http://x')\ng = None", ExecutionMode.BLOCKING_SYNC),
        ]
        for code, expected in cases:
            assert ex.analyze_execution_mode(code) == expected

    # ----------------- Complex attribute chains -----------------
    def test_requests_session_chain(self):
        ex = self.make_executor()
        code1 = """
import requests
requests.Session().get('http://example.com')
"""
        code2 = """
from requests import Session
Session().get('http://example.com')
"""
        assert ex.analyze_execution_mode(code1) == ExecutionMode.BLOCKING_SYNC
        assert ex.analyze_execution_mode(code2) == ExecutionMode.BLOCKING_SYNC
