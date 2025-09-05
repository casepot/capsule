import pytest

from src.subprocess.async_executor import AsyncExecutor, ExecutionMode
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
class TestBlockingIODetectionBreadth:
    def _executor(self):
        return AsyncExecutor(namespace_manager=NamespaceManager(), transport=None, execution_id="det-breadth")

    def test_alias_imports_detection(self):
        ex = self._executor()
        assert ex.analyze_execution_mode("import requests as rq; rq.get('http://example.com')") == ExecutionMode.BLOCKING_SYNC
        assert ex.analyze_execution_mode("from requests import get as g; g('http://example.com')") == ExecutionMode.BLOCKING_SYNC

    def test_chained_calls_socket_recv(self):
        ex = self._executor()
        code = "import socket\ns = socket.socket()\nb = s.recv(1)"
        assert ex.analyze_execution_mode(code) == ExecutionMode.BLOCKING_SYNC

    def test_urllib_request_urlopen(self):
        ex = self._executor()
        code = "from urllib.request import urlopen\nr = urlopen('http://example.com')"
        assert ex.analyze_execution_mode(code) == ExecutionMode.BLOCKING_SYNC

    def test_time_sleep_detection(self):
        ex = self._executor()
        assert ex.analyze_execution_mode("import time; time.sleep(0.01)") == ExecutionMode.BLOCKING_SYNC
        assert ex.analyze_execution_mode("from time import sleep; sleep(0.01)") == ExecutionMode.BLOCKING_SYNC

    def test_os_system_and_subprocess(self):
        ex = self._executor()
        assert ex.analyze_execution_mode("import os; os.system('true')") == ExecutionMode.BLOCKING_SYNC
        assert ex.analyze_execution_mode("import subprocess; subprocess.run(['true'])") == ExecutionMode.BLOCKING_SYNC
        assert ex.analyze_execution_mode("from subprocess import Popen; Popen(['true'])") == ExecutionMode.BLOCKING_SYNC

    def test_pathlib_path_read(self):
        ex = self._executor()
        assert ex.analyze_execution_mode("from pathlib import Path; Path('f').read_text()") == ExecutionMode.BLOCKING_SYNC

    def test_negative_controls(self):
        ex = self._executor()
        assert ex.analyze_execution_mode("import math; x = math.sqrt(4)") == ExecutionMode.SIMPLE_SYNC
        assert ex.analyze_execution_mode("import json; s = json.dumps({'a':1})") == ExecutionMode.SIMPLE_SYNC


@pytest.mark.unit
def test_telemetry_counters_increment():
    ex = AsyncExecutor(namespace_manager=NamespaceManager(), transport=None, execution_id="telemetry")
    # Blocking import
    assert ex.analyze_execution_mode("import requests") == ExecutionMode.BLOCKING_SYNC
    assert ex.stats["detected_blocking_import"] >= 1
    # Blocking call
    before = ex.stats["detected_blocking_call"]
    assert ex.analyze_execution_mode("import time; time.sleep(0.01)") == ExecutionMode.BLOCKING_SYNC
    assert ex.stats["detected_blocking_call"] == before + 1


@pytest.mark.unit
def test_missed_attribute_chain_counter():
    ex = AsyncExecutor(namespace_manager=NamespaceManager(), transport=None, execution_id="telemetry2")
    before = ex.stats["missed_attribute_chain"]
    # Attribute call with non-name base; should not be flagged as blocking but counts as missed chain
    mode = ex.analyze_execution_mode("result = (1+2).bit_length()")
    assert mode == ExecutionMode.SIMPLE_SYNC
    assert ex.stats["missed_attribute_chain"] >= before
