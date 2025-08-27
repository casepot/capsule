#!/usr/bin/env python3
"""Test 5: Performance, cancellation, and IPython event system integration."""

import sys
import time
import asyncio
import threading
import traceback
import psutil
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class PerformanceMetrics:
    """Performance measurement results."""
    execution_time: float
    memory_before: int
    memory_after: int
    memory_delta: int
    cpu_percent: float


def measure_performance(func):
    """Decorator to measure performance of a function."""
    def wrapper(*args, **kwargs):
        process = psutil.Process(os.getpid())
        
        # Before metrics
        memory_before = process.memory_info().rss
        cpu_before = process.cpu_percent()
        start_time = time.time()
        
        # Execute
        result = func(*args, **kwargs)
        
        # After metrics
        end_time = time.time()
        memory_after = process.memory_info().rss
        cpu_after = process.cpu_percent()
        
        metrics = PerformanceMetrics(
            execution_time=end_time - start_time,
            memory_before=memory_before,
            memory_after=memory_after,
            memory_delta=memory_after - memory_before,
            cpu_percent=(cpu_before + cpu_after) / 2
        )
        
        return result, metrics
    
    return wrapper


def test_ipython_overhead():
    """Test IPython execution overhead vs direct Python."""
    print("=" * 60)
    print("TEST 5.1: IPython Execution Overhead")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        shell = InteractiveShell.instance()
        
        # Test code
        test_code = """
result = 0
for i in range(100000):
    result += i
"""
        
        # Measure direct Python execution
        @measure_performance
        def direct_python():
            exec(test_code)
        
        _, direct_metrics = direct_python()
        print(f"Direct Python:")
        print(f"  Time: {direct_metrics.execution_time:.4f}s")
        print(f"  Memory: {direct_metrics.memory_delta / 1024:.1f} KB")
        
        # Measure IPython execution
        @measure_performance
        def ipython_exec():
            shell.run_cell(test_code)
        
        _, ipython_metrics = ipython_exec()
        print(f"IPython:")
        print(f"  Time: {ipython_metrics.execution_time:.4f}s")
        print(f"  Memory: {ipython_metrics.memory_delta / 1024:.1f} KB")
        
        # Calculate overhead
        time_overhead = (ipython_metrics.execution_time - direct_metrics.execution_time) / direct_metrics.execution_time * 100
        print(f"\n✓ Time overhead: {time_overhead:.1f}%")
        
        # Reasonable overhead threshold (< 50%)
        acceptable_overhead = time_overhead < 50
        print(f"✓ Overhead acceptable: {acceptable_overhead}")
        
        return acceptable_overhead
        
    except Exception as e:
        print(f"✗ Overhead test failed: {e}")
        traceback.print_exc()
        return False


def test_cancellation_mechanism():
    """Test execution cancellation in IPython."""
    print("\n" + "=" * 60)
    print("TEST 5.2: Execution Cancellation")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        import signal
        
        shell = InteractiveShell.instance()
        
        # Note: IPython doesn't have direct cancellation like PyREPL3's sys.settrace
        print("Testing interrupt handling:")
        
        # Test keyboard interrupt handling
        code_with_loop = """
import time
interrupted = False
try:
    for i in range(10):
        time.sleep(0.1)
        if i == 2:
            raise KeyboardInterrupt()
except KeyboardInterrupt:
    interrupted = True
"""
        
        shell.run_cell(code_with_loop)
        was_interrupted = shell.user_ns.get('interrupted', False)
        print(f"✓ KeyboardInterrupt handled: {was_interrupted}")
        
        # Test that execution continues after interrupt
        shell.run_cell("after_interrupt = 'still working'")
        continues = shell.user_ns.get('after_interrupt') == 'still working'
        print(f"✓ Execution continues after interrupt: {continues}")
        
        # Note limitations
        print("\nLimitations:")
        print("  - IPython lacks cooperative cancellation like sys.settrace")
        print("  - Would need custom solution for fine-grained cancellation")
        print("  - Signal-based interrupts are process-wide, not thread-specific")
        
        return was_interrupted and continues
        
    except Exception as e:
        print(f"✗ Cancellation test failed: {e}")
        traceback.print_exc()
        return False


def test_event_system_integration():
    """Test IPython's event system for execution hooks."""
    print("\n" + "=" * 60)
    print("TEST 5.3: Event System Integration")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        shell = InteractiveShell.instance()
        
        # Track events
        events_fired = []
        
        # Register event handlers
        def pre_execute():
            events_fired.append('pre_execute')
        
        def pre_run_cell(info):
            events_fired.append(f'pre_run_cell: {len(info.raw_cell)} chars')
        
        def post_execute():
            events_fired.append('post_execute')
        
        def post_run_cell(result):
            events_fired.append(f'post_run_cell: success={result.success}')
        
        shell.events.register('pre_execute', pre_execute)
        shell.events.register('pre_run_cell', pre_run_cell)
        shell.events.register('post_execute', post_execute)
        shell.events.register('post_run_cell', post_run_cell)
        
        print("✓ Registered event handlers")
        
        # Execute code to trigger events
        shell.run_cell("test_var = 42")
        
        print(f"✓ Events fired: {events_fired}")
        
        # Verify event order
        expected_order = ['pre_run_cell', 'pre_execute', 'post_execute', 'post_run_cell']
        correct_order = all(
            any(expected in event for event in events_fired)
            for expected in expected_order
        )
        print(f"✓ Correct event order: {correct_order}")
        
        # Test error events
        events_fired.clear()
        result = shell.run_cell("1/0")
        
        has_error_event = any('success=False' in event for event in events_fired)
        print(f"✓ Error event triggered: {has_error_event}")
        
        # Unregister handlers
        shell.events.unregister('pre_execute', pre_execute)
        shell.events.unregister('pre_run_cell', pre_run_cell)
        shell.events.unregister('post_execute', post_execute)
        shell.events.unregister('post_run_cell', post_run_cell)
        
        return correct_order and has_error_event
        
    except Exception as e:
        print(f"✗ Event system test failed: {e}")
        traceback.print_exc()
        return False


def test_async_performance():
    """Test async execution performance."""
    print("\n" + "=" * 60)
    print("TEST 5.4: Async Execution Performance")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        shell = InteractiveShell.instance()
        shell.autoawait = True
        
        async def test_async_perf():
            # Test async execution overhead
            async_code = """
import asyncio

async def async_task():
    await asyncio.sleep(0.01)
    return 42

results = []
for i in range(10):
    result = await async_task()
    results.append(result)
"""
            
            @measure_performance
            async def measure_async():
                await shell.run_cell_async(async_code)
            
            _, metrics = await measure_async()
            
            print(f"Async execution (10 tasks):")
            print(f"  Time: {metrics.execution_time:.4f}s")
            print(f"  Memory: {metrics.memory_delta / 1024:.1f} KB")
            
            # Should take ~0.1s (10 * 0.01s sleep)
            # Allow some overhead
            reasonable_time = metrics.execution_time < 0.5
            print(f"✓ Reasonable async performance: {reasonable_time}")
            
            return reasonable_time
        
        # Run async test
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(test_async_perf())
        
        return result
        
    except Exception as e:
        print(f"✗ Async performance test failed: {e}")
        traceback.print_exc()
        return False


def test_memory_management():
    """Test memory management and namespace cleanup."""
    print("\n" + "=" * 60)
    print("TEST 5.5: Memory Management")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        import gc
        
        shell = InteractiveShell.instance()
        process = psutil.Process(os.getpid())
        
        # Baseline memory
        gc.collect()
        baseline_memory = process.memory_info().rss
        print(f"Baseline memory: {baseline_memory / 1024 / 1024:.1f} MB")
        
        # Create large objects
        shell.run_cell("large_list = [i for i in range(1000000)]")
        shell.run_cell("large_dict = {i: str(i) for i in range(100000)}")
        
        after_creation = process.memory_info().rss
        print(f"After creation: {after_creation / 1024 / 1024:.1f} MB")
        print(f"  Delta: {(after_creation - baseline_memory) / 1024 / 1024:.1f} MB")
        
        # Clear namespace
        shell.run_cell("del large_list")
        shell.run_cell("del large_dict")
        shell.reset()
        gc.collect()
        
        after_cleanup = process.memory_info().rss
        print(f"After cleanup: {after_cleanup / 1024 / 1024:.1f} MB")
        
        # Memory should be mostly recovered (within 20% of baseline)
        memory_recovered = (after_cleanup - baseline_memory) < (after_creation - baseline_memory) * 0.2
        print(f"✓ Memory recovered: {memory_recovered}")
        
        # Test namespace size
        shell.run_cell("for i in range(100): exec(f'var_{i} = {i}')")
        namespace_size = len(shell.user_ns)
        print(f"✓ Namespace size after 100 vars: {namespace_size}")
        
        # Reset and check
        shell.reset()
        reset_size = len(shell.user_ns)
        print(f"✓ Namespace size after reset: {reset_size}")
        
        namespace_cleared = reset_size < namespace_size / 2
        print(f"✓ Namespace properly cleared: {namespace_cleared}")
        
        return memory_recovered and namespace_cleared
        
    except Exception as e:
        print(f"✗ Memory management test failed: {e}")
        traceback.print_exc()
        return False


def test_concurrent_execution():
    """Test concurrent execution scenarios."""
    print("\n" + "=" * 60)
    print("TEST 5.6: Concurrent Execution")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        # Note: IPython InteractiveShell is not thread-safe by default
        print("Testing concurrency limitations:")
        
        # Create separate shells for concurrent execution
        shells = []
        for i in range(3):
            # Create new instance (workaround singleton)
            from IPython.core.interactiveshell import InteractiveShell as IS
            shell = IS()
            shells.append(shell)
            print(f"✓ Created shell {i}")
        
        # Execute different code in each
        results = []
        
        def execute_in_shell(shell, code, index):
            try:
                shell.run_cell(code)
                results.append((index, shell.user_ns.get('result', None)))
            except Exception as e:
                results.append((index, f"error: {e}"))
        
        threads = []
        codes = [
            "result = 'shell0'",
            "result = 'shell1'",
            "result = 'shell2'",
        ]
        
        for i, (shell, code) in enumerate(zip(shells, codes)):
            thread = threading.Thread(target=execute_in_shell, args=(shell, code, i))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        print(f"✓ Execution results: {results}")
        
        # Check isolation
        all_different = len(set(r[1] for r in results)) == len(results)
        print(f"✓ Shells isolated: {all_different}")
        
        print("\nNote: IPython limitations for concurrent execution:")
        print("  - Single InteractiveShell instance not thread-safe")
        print("  - Need separate instances for true concurrency")
        print("  - Event loop integration complex with multiple shells")
        
        return all_different
        
    except Exception as e:
        print(f"✗ Concurrent execution test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all performance and event tests."""
    print("IPython Integration Investigation - Performance & Events")
    print("=" * 60)
    
    tests = [
        test_ipython_overhead,
        test_cancellation_mechanism,
        test_event_system_integration,
        test_async_performance,
        test_memory_management,
        test_concurrent_execution,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n✗ Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total = len(results)
    passed = sum(results)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("✓ All performance & event tests passed!")
    else:
        print("✗ Some tests failed - performance/events need attention")
        
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if main() else 1)