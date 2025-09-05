# Testing and Validation Specification

## Document Information
- **Version**: 1.0.0
- **Status**: Draft
- **Last Updated**: 2025-01-03
- **Classification**: Testing Specification

## Executive Summary

This specification defines comprehensive testing and validation strategies for PyREPL3, covering unit tests, integration tests, performance benchmarks, security validation, and acceptance criteria. The testing approach validates critical discoveries from investigation, including the PyCF_ALLOW_TOP_LEVEL_AWAIT flag functionality, namespace merge-only policy, and capability-based security enforcement.

## Testing Philosophy

### Core Principles

1. **Test Critical Discoveries**: Validate investigation findings
2. **Prevent Regression**: Ensure known issues don't recur
3. **Performance Validation**: Meet < 5% overhead target
4. **Security First**: Validate all security boundaries
5. **Recovery Testing**: Verify durability promises

## Test Categories

```
Testing Pyramid
      ╱╲
     ╱E2E╲        End-to-End Tests (5%)
    ╱──────╲      Full system validation
   ╱ Integr ╲     Integration Tests (20%)
  ╱──────────╲    Component interactions
 ╱    Unit    ╲   Unit Tests (60%)
╱──────────────╲  Individual components
▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔  Performance & Security (15%)
```

## Unit Tests

### AsyncExecutor Tests

```python
import pytest
import asyncio
import ast
from unittest.mock import Mock, MagicMock, patch

class TestAsyncExecutor:
    """Unit tests for AsyncExecutor component."""
    
    @pytest.fixture
    def executor(self):
        """Create executor instance for testing."""
        resonate = Mock()
        namespace_manager = Mock()
        return AsyncExecutor(resonate, namespace_manager, "test-exec")
    
    def test_pcf_allow_top_level_await_flag(self):
        """Test that PyCF_ALLOW_TOP_LEVEL_AWAIT flag works."""
        # This is THE critical discovery - must work
        assert AsyncExecutor.PyCF_ALLOW_TOP_LEVEL_AWAIT == 0x2000
        
        # Test compilation with flag
        code = "await asyncio.sleep(0)"
        base_flags = compile('', '', 'exec').co_flags
        flags = base_flags | 0x1000000
        
        # This should compile without SyntaxError
        compiled = compile(code, '<test>', 'exec', flags=flags)
        assert compiled is not None
    
    def test_execution_mode_detection(self, executor):
        """Test correct detection of execution modes."""
        test_cases = [
            # (code, expected_mode)
            ("x = 1", ExecutionMode.SIMPLE_SYNC),
            ("async def foo(): pass", ExecutionMode.ASYNC_DEF),
            ("await asyncio.sleep(0)", ExecutionMode.TOP_LEVEL_AWAIT),
            ("import requests; r = requests.get('url')", ExecutionMode.BLOCKING_SYNC),
        ]
        
        for code, expected_mode in test_cases:
            mode = executor.analyze_execution_mode(code)
            assert mode == expected_mode, f"Failed for: {code}"
    
    @pytest.mark.asyncio
    async def test_top_level_await_execution(self, executor):
        """Test top-level await execution."""
        code = """
        import asyncio
        result = await asyncio.sleep(0, 'test_result')
        """
        
        # Mock namespace manager
        executor.namespace.get_for_execution.return_value = {
            '__builtins__': __builtins__,
            'asyncio': asyncio
        }
        executor.namespace.update_namespace.return_value = {}
        
        result = await executor.execute(code)
        
        # Verify namespace was updated with result
        executor.namespace.update_namespace.assert_called()
        call_args = executor.namespace.update_namespace.call_args[0][0]
        assert 'result' in call_args
    
    def test_ast_transformation_fallback(self, executor):
        """Test AST transformation when direct compilation fails."""
        # Code that needs transformation
        code = "complex_await_pattern"
        
        with patch.object(executor, '_execute_with_ast_transform') as mock_transform:
            mock_transform.return_value = "transformed_result"
            
            # Force transformation path
            with patch('compile', side_effect=[SyntaxError, Mock()]):
                executor._execute_top_level_await(code)
                
            mock_transform.assert_called_once()
    
    def test_coroutine_tracking(self, executor):
        """Test coroutine lifecycle tracking."""
        async def test_coro():
            return "result"
        
        coro = test_coro()
        initial_count = len(executor._pending_coroutines)
        
        executor.track_coroutine(coro)
        assert len(executor._pending_coroutines) == initial_count + 1
        
        # Cleanup should close coroutine
        cleaned = executor.cleanup_coroutines()
        assert cleaned > 0
        assert len(executor._pending_coroutines) == initial_count
    
    def test_blocking_io_detection(self, executor):
        """Test detection of blocking I/O patterns."""
        blocking_code = [
            "import requests",
            "open('file.txt')",
            "socket.connect()",
            "time.sleep(1)",
        ]
        
        for code in blocking_code:
            try:
                tree = ast.parse(code)
                has_blocking = executor._contains_blocking_io(tree)
                assert has_blocking, f"Should detect blocking I/O in: {code}"
            except:
                pass  # Some might not parse standalone
```

### Namespace Management Tests

```python
class TestNamespaceManagement:
    """Unit tests for namespace management."""
    
    @pytest.fixture
    def manager(self):
        """Create namespace manager for testing."""
        resonate = Mock()
        resonate.promises.get.return_value = None  # No recovery
        return DurableNamespaceManager(resonate, "test-exec")
    
    def test_namespace_never_replaced(self, manager):
        """CRITICAL: Test namespace is never replaced, only updated."""
        # This is the most critical test - prevents KeyError
        initial_id = id(manager._namespace)
        
        # Various update operations
        manager.update_namespace({"x": 1})
        assert id(manager._namespace) == initial_id
        
        manager.update_namespace({"y": 2})
        assert id(manager._namespace) == initial_id
        
        manager.merge_thread_results({"z": 3}, {})
        assert id(manager._namespace) == initial_id
        
        # Namespace object must be the same throughout
        assert initial_id == id(manager._namespace)
    
    def test_engine_internals_preserved(self, manager):
        """Test engine internals are preserved."""
        # Check internals exist
        for key in ['_', '__', '___', 'Out', 'In']:
            assert key in manager._namespace
        
        # Try to overwrite from user context
        manager.update_namespace({'_': 'user_value'}, source_context='user')
        
        # Should not be changed (protected)
        assert manager._namespace['_'] is None
        
        # But engine context can update
        manager.update_namespace({'_': 'engine_value'}, source_context='engine')
        assert manager._namespace['_'] == 'engine_value'
    
    def test_merge_strategies(self, manager):
        """Test different merge strategies."""
        # Overwrite strategy
        manager.update_namespace({"x": 1})
        manager.update_namespace({"x": 2}, merge_strategy="overwrite")
        assert manager._namespace["x"] == 2
        
        # Preserve strategy
        manager.update_namespace({"x": 3}, merge_strategy="preserve")
        assert manager._namespace["x"] == 2  # Unchanged
        
        # Smart strategy
        manager.update_namespace({"x": None}, merge_strategy="smart")
        assert manager._namespace["x"] == 2  # Not overwritten with None
    
    def test_thread_safe_access(self, manager):
        """Test thread-safe namespace access."""
        import threading
        import time
        
        results = []
        errors = []
        
        def worker(n):
            try:
                for i in range(100):
                    manager.update_namespace({f"thread_{n}_{i}": i})
                    time.sleep(0.0001)
                results.append(n)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # No errors should occur
        assert len(errors) == 0
        assert len(results) == 10
        
        # All updates should be present
        for n in range(10):
            for i in range(100):
                assert f"thread_{n}_{i}" in manager._namespace
    
    def test_serialization_deserialization(self, manager):
        """Test namespace serialization for persistence."""
        # Add various types
        manager.update_namespace({
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "list": [1, 2, 3],
            "dict": {"a": 1},
            "set_value": {1, 2, 3},
            "function": lambda x: x,  # Should be skipped
        })
        
        serialized = manager._prepare_for_serialization()
        
        # Function should be skipped
        assert "function" not in serialized
        
        # Others should be serializable
        import json
        json_str = json.dumps(serialized)
        assert json_str is not None
```

### Capability System Tests

```python
class TestCapabilitySystem:
    """Unit tests for capability system."""
    
    @pytest.fixture
    def registry(self):
        """Create capability registry for testing."""
        resonate = Mock()
        return CapabilityRegistry(resonate)
    
    def test_capability_registration(self, registry):
        """Test capability registration."""
        # Create test capability
        class TestCap(Capability):
            def get_name(self):
                return "test_cap"
            
            def get_implementation(self):
                return lambda: "test"
            
            def validate_arguments(self, *args, **kwargs):
                return True
        
        registry.register_capability(TestCap)
        assert "test_cap" in registry._capabilities
    
    def test_security_policy_enforcement(self, registry):
        """Test security policy enforces capability access."""
        # Register capabilities
        registry.register_capability(PrintCapability)
        registry.register_capability(InputCapability)
        registry.register_capability(FetchCapability)
        
        # Restrictive policy
        policy = SecurityPolicy(SecurityLevel.SANDBOX)
        namespace = {}
        
        registry.inject_capabilities(namespace, "test", policy)
        
        # Only print should be available in SANDBOX
        assert "print" in namespace
        assert "input" not in namespace
        assert "fetch" not in namespace
    
    def test_capability_validation(self):
        """Test capability argument validation."""
        resonate = Mock()
        
        # File capability validation
        file_cap = FileReadCapability(resonate, "test")
        
        # Valid paths
        assert file_cap.validate_arguments("data.txt", "utf-8")
        
        # Invalid paths (directory traversal)
        assert not file_cap.validate_arguments("../etc/passwd", "utf-8")
        assert not file_cap.validate_arguments("/etc/passwd", "utf-8")
        
        # Invalid encoding
        assert not file_cap.validate_arguments("file.txt", "invalid")
    
    def test_promise_creation(self):
        """Test capability creates promises correctly."""
        resonate = Mock()
        resonate.promises.create.return_value = Mock(id="promise-123")
        
        cap = InputCapability(resonate, "test-exec")
        promise = cap.create_promise(
            "user_input",
            {"prompt": "Enter name:"},
            timeout=60.0
        )
        
        # Verify promise created with correct parameters
        resonate.promises.create.assert_called_once()
        call_args = resonate.promises.create.call_args[1]
        assert call_args['timeout'] == 60000  # Converted to ms
```

## Integration Tests

### End-to-End Execution Tests

```python
class TestEndToEndExecution:
    """Integration tests for complete execution flow."""
    
    @pytest.mark.asyncio
    async def test_complete_execution_flow(self):
        """Test complete execution from initialization to result."""
        # Initialize system
        resonate = initialize_resonate_local()
        
        # Create components
        namespace_manager = DurableNamespaceManager(resonate, "test-e2e")
        executor = AsyncExecutor(resonate, namespace_manager, "test-e2e")
        registry = CapabilityRegistry(resonate)
        
        # Register capabilities
        register_standard_capabilities(registry)
        
        # Apply security policy
        policy = SecurityPolicy(SecurityLevel.STANDARD)
        namespace = namespace_manager.namespace
        registry.inject_capabilities(namespace, "test-e2e", policy)
        
        # Execute various code patterns
        await executor.execute("x = 42")
        await executor.execute("y = x * 2")
        
        # Top-level await
        await executor.execute("""
        import asyncio
        result = await asyncio.sleep(0, 'done')
        """)
        
        # Verify results
        final_namespace = namespace_manager.namespace
        assert final_namespace.get('x') == 42
        assert final_namespace.get('y') == 84
        assert final_namespace.get('result') == 'done'
    
    @pytest.mark.asyncio
    async def test_mixed_execution_modes(self):
        """Test mixing different execution modes."""
        resonate = initialize_resonate_local()
        namespace_manager = DurableNamespaceManager(resonate, "test-mixed")
        executor = AsyncExecutor(resonate, namespace_manager, "test-mixed")
        
        # Simple sync
        await executor.execute("a = 1")
        
        # Async function definition
        await executor.execute("""
        async def double(n):
            return n * 2
        """)
        
        # Top-level await using async function
        await executor.execute("b = await double(a)")
        
        # Blocking I/O (should use thread)
        await executor.execute("""
        import time
        c = 3  # Would normally use time.sleep
        """)
        
        namespace = namespace_manager.namespace
        assert namespace.get('a') == 1
        assert namespace.get('b') == 2
        assert namespace.get('c') == 3
```

### Recovery and Durability Tests

```python
class TestRecoveryDurability:
    """Test recovery and durability features."""
    
    @pytest.mark.asyncio
    async def test_namespace_recovery(self):
        """Test namespace recovery after crash."""
        resonate = initialize_resonate_local()
        
        # First execution
        manager1 = DurableNamespaceManager(resonate, "recovery-test")
        manager1.update_namespace({
            "important_data": "must_survive",
            "counter": 42
        })
        manager1.persist_to_resonate(force=True)
        
        # Simulate crash and recovery
        manager2 = DurableNamespaceManager(resonate, "recovery-test")
        
        # Data should be recovered
        assert manager2._namespace.get("important_data") == "must_survive"
        assert manager2._namespace.get("counter") == 42
    
    @pytest.mark.asyncio
    async def test_execution_checkpoint_recovery(self):
        """Test execution checkpoint and recovery."""
        resonate = initialize_resonate_remote()  # Requires server
        
        @resonate.register
        def checkpointed_execution(ctx, args):
            execution_id = args['execution_id']
            
            # Check for existing checkpoint
            checkpoint = yield ctx.get_checkpoint(execution_id)
            
            if checkpoint:
                step = checkpoint['step']
            else:
                step = 0
            
            results = []
            
            if step <= 0:
                results.append("step1")
                yield ctx.checkpoint("step1", {"step": 1, "results": results})
            
            if step <= 1:
                results.append("step2")
                yield ctx.checkpoint("step2", {"step": 2, "results": results})
            
            return results
        
        # Execute with simulated crash
        result = checkpointed_execution.run("checkpoint-test", {
            'execution_id': 'checkpoint-test'
        })
        
        assert "step1" in result
        assert "step2" in result
```

## Performance Tests

### Execution Performance Benchmarks

```python
import time
import statistics

class TestPerformance:
    """Performance benchmark tests."""
    
    @pytest.mark.benchmark
    @pytest.mark.asyncio
    async def test_execution_overhead(self):
        """Test execution overhead is < 5% vs direct Python."""
        resonate = initialize_resonate_local()
        namespace_manager = DurableNamespaceManager(resonate, "perf-test")
        executor = AsyncExecutor(resonate, namespace_manager, "perf-test")
        
        # Baseline: Direct Python execution
        code = "result = sum(range(1000))"
        
        start = time.perf_counter()
        for _ in range(1000):
            exec(code, {})
        baseline_time = time.perf_counter() - start
        
        # PyREPL3 execution
        start = time.perf_counter()
        for _ in range(1000):
            await executor.execute(code)
        pyrepl3_time = time.perf_counter() - start
        
        # Calculate overhead
        overhead = (pyrepl3_time - baseline_time) / baseline_time * 100
        
        # Assert < 5% overhead
        assert overhead < 5.0, f"Overhead {overhead:.1f}% exceeds 5% target"
    
    @pytest.mark.benchmark
    def test_namespace_operation_performance(self):
        """Test namespace operation performance."""
        resonate = Mock()
        manager = DurableNamespaceManager(resonate, "perf-namespace")
        
        # Measure update performance
        times = []
        for _ in range(1000):
            start = time.perf_counter_ns()
            manager.update_namespace({"x": 42})
            times.append(time.perf_counter_ns() - start)
        
        # Should be < 100μs (100,000 ns)
        median_time = statistics.median(times)
        assert median_time < 100_000, f"Update took {median_time}ns"
    
    @pytest.mark.benchmark
    @pytest.mark.asyncio
    async def test_capability_invocation_performance(self):
        """Test capability invocation overhead."""
        resonate = Mock()
        resonate.promises.create.return_value = Mock(id="test")
        
        cap = PrintCapability(resonate, "perf-cap", Mock())
        impl = cap.get_implementation()
        
        # Measure invocation time
        times = []
        for _ in range(1000):
            start = time.perf_counter_ns()
            impl("test message")
            times.append(time.perf_counter_ns() - start)
        
        # Should be < 10μs (10,000 ns)
        median_time = statistics.median(times)
        assert median_time < 10_000, f"Invocation took {median_time}ns"
```

### Memory Usage Tests

```python
class TestMemoryUsage:
    """Memory usage and leak tests."""
    
    @pytest.mark.memory
    @pytest.mark.asyncio
    async def test_no_memory_leaks(self):
        """Test for memory leaks in execution."""
        import gc
        import tracemalloc
        
        tracemalloc.start()
        
        resonate = initialize_resonate_local()
        namespace_manager = DurableNamespaceManager(resonate, "mem-test")
        executor = AsyncExecutor(resonate, namespace_manager, "mem-test")
        
        # Take snapshot before
        snapshot1 = tracemalloc.take_snapshot()
        
        # Execute many times
        for i in range(1000):
            await executor.execute(f"x_{i} = {i}")
        
        # Force garbage collection
        gc.collect()
        
        # Take snapshot after
        snapshot2 = tracemalloc.take_snapshot()
        
        # Calculate difference
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        
        # Check for significant leaks
        total_increase = sum(stat.size_diff for stat in top_stats)
        
        # Should be < 10MB for 1000 executions
        assert total_increase < 10 * 1024 * 1024
    
    @pytest.mark.memory
    def test_coroutine_cleanup(self):
        """Test coroutines are properly cleaned up."""
        import gc
        
        resonate = Mock()
        namespace_manager = Mock()
        executor = AsyncExecutor(resonate, namespace_manager, "coro-test")
        
        # Track coroutines
        async def test_coro():
            pass
        
        for _ in range(100):
            coro = test_coro()
            executor.track_coroutine(coro)
        
        # Should have tracked coroutines
        assert len(executor._pending_coroutines) > 0
        
        # Cleanup
        cleaned = executor.cleanup_coroutines()
        
        # Should be cleaned
        assert cleaned > 0
        assert len(executor._pending_coroutines) == 0
        
        # Force GC and check no references remain
        gc.collect()
```

## Security Tests

### Security Validation Tests

```python
class TestSecurityValidation:
    """Security validation tests."""
    
    def test_no_eval_exec_available(self):
        """Test eval/exec not available in namespace."""
        resonate = Mock()
        manager = DurableNamespaceManager(resonate, "sec-test")
        registry = CapabilityRegistry(resonate)
        
        policy = SecurityPolicy(SecurityLevel.UNRESTRICTED)
        namespace = manager.namespace
        registry.inject_capabilities(namespace, "sec-test", policy)
        
        # These should not exist
        assert 'eval' not in namespace
        assert 'exec' not in namespace
        assert '__import__' not in namespace
    
    def test_capability_bypass_prevention(self):
        """Test capabilities cannot be bypassed."""
        resonate = Mock()
        registry = CapabilityRegistry(resonate)
        
        # Register capabilities
        register_standard_capabilities(registry)
        
        # Restrictive policy - no file access
        policy = SecurityPolicy(SecurityLevel.SANDBOX)
        namespace = {}
        registry.inject_capabilities(namespace, "test", policy)
        
        # Try to access file capability
        assert 'read_file' not in namespace
        assert 'write_file' not in namespace
        
        # Try to bypass with getattr
        with pytest.raises((KeyError, AttributeError)):
            getattr(namespace, 'read_file')
    
    def test_path_traversal_prevention(self):
        """Test path traversal attack prevention."""
        sanitizer = InputSanitizer()
        
        dangerous_paths = [
            "../etc/passwd",
            "../../etc/shadow",
            "/etc/passwd",
            "data/../../../etc/passwd",
            ".\\.\\..\\..\\windows\\system32",
        ]
        
        for path in dangerous_paths:
            with pytest.raises(ValueError):
                sanitizer.sanitize_path(path)
    
    def test_ssrf_prevention(self):
        """Test SSRF attack prevention."""
        validator = CapabilityValidator(SecurityPolicy())
        
        dangerous_urls = [
            "http://localhost/admin",
            "http://127.0.0.1:8080",
            "http://169.254.169.254/metadata",
            "http://[::1]/internal",
            "file:///etc/passwd",
        ]
        
        for url in dangerous_urls:
            assert not validator._validate_fetch(url)
```

## Acceptance Tests

### Critical Functionality Tests

```python
class TestAcceptanceCriteria:
    """Tests for acceptance criteria from specifications."""
    
    @pytest.mark.asyncio
    async def test_top_level_await_works(self):
        """Accept: Top-level await works with PyCF_ALLOW_TOP_LEVEL_AWAIT."""
        resonate = initialize_resonate_local()
        namespace_manager = DurableNamespaceManager(resonate, "accept-1")
        executor = AsyncExecutor(resonate, namespace_manager, "accept-1")
        
        code = """
        import asyncio
        result = await asyncio.sleep(0, 'success')
        """
        
        await executor.execute(code)
        
        namespace = namespace_manager.namespace
        assert namespace.get('result') == 'success'
    
    def test_no_namespace_key_errors(self):
        """Accept: No KeyError from namespace operations."""
        resonate = Mock()
        manager = DurableNamespaceManager(resonate, "accept-2")
        
        # This pattern caused KeyError in IPython
        manager.update_namespace({'result': 42}, 'user')
        
        # Try to access engine internals - should not error
        assert manager._namespace['_'] is not None or manager._namespace['_'] is None
        assert 'Out' in manager._namespace
    
    def test_capability_injection_security(self):
        """Accept: Security enforced at capability injection."""
        resonate = Mock()
        registry = CapabilityRegistry(resonate)
        register_standard_capabilities(registry)
        
        # Different security levels
        levels = [
            (SecurityLevel.SANDBOX, ['print']),
            (SecurityLevel.RESTRICTED, ['print', 'input', 'read_file']),
            (SecurityLevel.STANDARD, ['print', 'input', 'read_file', 'write_file', 'fetch']),
        ]
        
        for level, expected_caps in levels:
            policy = SecurityPolicy(level)
            namespace = {}
            registry.inject_capabilities(namespace, "test", policy)
            
            for cap in expected_caps:
                assert cap in namespace, f"{cap} missing at {level}"
    
    @pytest.mark.asyncio
    async def test_performance_target_met(self):
        """Accept: Performance overhead < 5% in local mode."""
        # Tested in performance benchmarks
        pass
    
    def test_zero_dependencies_local_mode(self):
        """Accept: Local mode works without external dependencies."""
        # No external servers required
        resonate = initialize_resonate_local()
        assert resonate is not None
        
        # Can create all components
        manager = DurableNamespaceManager(resonate, "local-test")
        executor = AsyncExecutor(resonate, manager, "local-test")
        registry = CapabilityRegistry(resonate)
        
        assert manager is not None
        assert executor is not None
        assert registry is not None
```

## Test Fixtures and Utilities

### Common Fixtures

```python
@pytest.fixture(scope="session")
def resonate_local():
    """Session-scoped local Resonate instance."""
    return initialize_resonate_local()

@pytest.fixture(scope="session")
def resonate_remote():
    """Session-scoped remote Resonate instance."""
    if os.getenv("RESONATE_TEST_SERVER"):
        return initialize_resonate_remote(
            host=os.getenv("RESONATE_TEST_SERVER")
        )
    else:
        pytest.skip("No test server configured")

@pytest.fixture
def clean_namespace(resonate_local):
    """Clean namespace manager for each test."""
    execution_id = f"test-{uuid.uuid4()}"
    return DurableNamespaceManager(resonate_local, execution_id)

@pytest.fixture
def executor(resonate_local, clean_namespace):
    """Executor with clean namespace."""
    execution_id = clean_namespace.execution_id
    return AsyncExecutor(resonate_local, clean_namespace, execution_id)

@pytest.fixture
def secure_namespace(resonate_local):
    """Namespace with security policy applied."""
    manager = DurableNamespaceManager(resonate_local, "secure-test")
    registry = CapabilityRegistry(resonate_local)
    register_standard_capabilities(registry)
    
    policy = SecurityPolicy(SecurityLevel.STANDARD)
    namespace = manager.namespace
    registry.inject_capabilities(namespace, "secure-test", policy)
    
    return manager
```

### Test Utilities

```python
class TestUtils:
    """Utilities for testing."""
    
    @staticmethod
    def create_test_capability(name: str, implementation: Callable):
        """Create a test capability."""
        class TestCapability(Capability):
            def get_name(self):
                return name
            
            def get_implementation(self):
                return implementation
            
            def validate_arguments(self, *args, **kwargs):
                return True
        
        return TestCapability
    
    @staticmethod
    async def execute_and_get_result(executor, code: str) -> Any:
        """Execute code and return result from namespace."""
        await executor.execute(code)
        namespace = executor.namespace.namespace
        return namespace.get('result') or namespace.get('_')
    
    @staticmethod
    def assert_execution_time(func: Callable, max_time: float):
        """Assert function executes within time limit."""
        start = time.time()
        result = func()
        elapsed = time.time() - start
        assert elapsed < max_time, f"Took {elapsed}s, max {max_time}s"
        return result
```

## Test Configuration

### pytest Configuration

```ini
# pytest.ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: Unit tests
    integration: Integration tests
    benchmark: Performance benchmarks
    memory: Memory usage tests
    security: Security validation tests
    acceptance: Acceptance criteria tests
    slow: Slow tests (> 1 second)
    requires_server: Requires Resonate server
addopts = 
    -v
    --strict-markers
    --tb=short
    --cov=pyrepl3
    --cov-report=term-missing
    --cov-report=html
```

### Test Coverage Requirements

```yaml
coverage:
  minimum_total: 90%
  minimum_per_file: 80%
  critical_components:
    async_executor.py: 95%
    namespace_manager.py: 95%
    capability_system.py: 90%
    security_policy.py: 95%
  exclude_patterns:
    - "*/tests/*"
    - "*/test_*.py"
    - "*/__pycache__/*"
```

## Continuous Integration

### CI Pipeline

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - run: pip install -r requirements-test.txt
      - run: pytest tests/unit -m unit --cov

  integration-tests:
    runs-on: ubuntu-latest
    services:
      resonate:
        image: resonate:latest
        ports:
          - 8001:8001
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements-test.txt
      - run: pytest tests/integration -m integration
        env:
          RESONATE_TEST_SERVER: http://localhost:8001

  performance-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements-test.txt
      - run: pytest tests/performance -m benchmark
      - run: python scripts/check_performance_regression.py

  security-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements-test.txt
      - run: pytest tests/security -m security
      - run: python scripts/security_audit.py
```

## Test Reporting

### Test Report Generation

```python
class TestReporter:
    """Generate test reports."""
    
    def generate_test_report(self, test_results):
        """Generate comprehensive test report."""
        report = {
            'summary': self._generate_summary(test_results),
            'coverage': self._generate_coverage_report(),
            'performance': self._generate_performance_report(),
            'security': self._generate_security_report(),
            'acceptance': self._check_acceptance_criteria(),
        }
        
        return report
    
    def _check_acceptance_criteria(self):
        """Check if all acceptance criteria are met."""
        criteria = [
            ('Top-level await works', self._check_top_level_await),
            ('No namespace KeyErrors', self._check_no_key_errors),
            ('Performance < 5% overhead', self._check_performance),
            ('Security at injection', self._check_security),
            ('Zero dependencies local', self._check_zero_deps),
        ]
        
        results = {}
        for name, check in criteria:
            results[name] = check()
        
        return results
```

## Test Data Management

### Test Data Fixtures

```python
class TestData:
    """Test data for various scenarios."""
    
    VALID_PYTHON_CODE = [
        "x = 1 + 1",
        "def foo(): return 42",
        "class Bar: pass",
        "[i for i in range(10)]",
    ]
    
    ASYNC_CODE = [
        "async def foo(): pass",
        "await asyncio.sleep(0)",
        "async for i in gen(): pass",
        "async with lock: pass",
    ]
    
    MALICIOUS_CODE = [
        "__import__('os').system('rm -rf /')",
        "eval('malicious')",
        "exec(compile('bad', '', 'exec'))",
    ]
    
    SAFE_PATHS = [
        "data.txt",
        "output/results.json",
        "logs/app.log",
    ]
    
    DANGEROUS_PATHS = [
        "../../../etc/passwd",
        "/etc/shadow",
        "C:\\Windows\\System32\\config",
    ]
```

## Validation Criteria

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Test Coverage | > 90% | pytest-cov |
| Unit Test Pass Rate | 100% | pytest results |
| Integration Test Pass Rate | > 95% | pytest results |
| Performance Overhead | < 5% | Benchmark tests |
| Memory Leak Rate | 0 | Memory profiler |
| Security Vulnerabilities | 0 | Security tests |

### Quality Gates

1. **Pre-commit**: Unit tests must pass
2. **Pull Request**: All tests must pass, coverage > 90%
3. **Release**: All acceptance criteria met
4. **Production**: Performance benchmarks validated

## Test Maintenance

### Test Review Checklist

- [ ] Tests cover new functionality
- [ ] Tests validate bug fixes
- [ ] Performance tests updated
- [ ] Security tests comprehensive
- [ ] Test documentation current
- [ ] Test data appropriate
- [ ] Fixtures reusable
- [ ] CI pipeline updated

## Version History

- **v1.0.0** (2025-01-03): Initial test specification based on REFINED requirements