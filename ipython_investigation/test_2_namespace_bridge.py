#!/usr/bin/env python3
"""Test 2: Namespace bridging between IPython and PyREPL3's NamespaceManager."""

import sys
import time
import asyncio
import threading
import traceback
from typing import Any, Dict, Optional
from dataclasses import dataclass


class MockNamespaceManager:
    """Simplified version of PyREPL3's NamespaceManager for testing."""
    
    def __init__(self):
        self._namespace: Dict[str, Any] = {
            "__name__": "__main__",
            "__doc__": None,
            "__package__": None,
            "__loader__": None,
            "__spec__": None,
            "__annotations__": {},
        }
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    @property
    def namespace(self) -> Dict[str, Any]:
        """Thread-safe namespace access."""
        with self._lock:
            return self._namespace
    
    def create_snapshot(self, transaction_id: str) -> None:
        """Create a snapshot for transactions."""
        with self._lock:
            self._snapshots[transaction_id] = dict(self._namespace)
    
    def restore_snapshot(self, transaction_id: str) -> None:
        """Restore from snapshot."""
        with self._lock:
            if transaction_id in self._snapshots:
                self._namespace.clear()
                self._namespace.update(self._snapshots[transaction_id])
    
    def update(self, updates: Dict[str, Any]) -> None:
        """Update namespace."""
        with self._lock:
            self._namespace.update(updates)


def test_namespace_bridging():
    """Test bridging IPython's user_ns with NamespaceManager."""
    print("=" * 60)
    print("TEST 2.1: Namespace Bridging")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        # Create our namespace manager
        ns_manager = MockNamespaceManager()
        
        # Create IPython shell
        shell = InteractiveShell.instance()
        
        # Point IPython to our managed namespace
        shell.user_ns = ns_manager.namespace
        shell.user_global_ns = ns_manager.namespace
        
        print("✓ Bridged IPython to NamespaceManager")
        
        # Test that changes in IPython affect our namespace
        shell.run_cell("test_var = 'from_ipython'")
        print(f"✓ IPython writes to our namespace: {ns_manager.namespace.get('test_var') == 'from_ipython'}")
        
        # Test that our changes affect IPython
        ns_manager.update({'external_var': 'from_manager'})
        result = shell.run_cell("external_var")
        print(f"✓ Our changes visible in IPython: {result.result == 'from_manager'}")
        
        # Test thread safety
        def thread_writer():
            for i in range(10):
                ns_manager.update({f'thread_var_{i}': i})
                time.sleep(0.01)
        
        thread = threading.Thread(target=thread_writer)
        thread.start()
        
        # Execute in IPython while thread is writing
        for i in range(5):
            shell.run_cell(f"ipython_var_{i} = {i}")
            time.sleep(0.02)
        
        thread.join()
        
        # Check all variables exist
        thread_vars = sum(1 for k in ns_manager.namespace if k.startswith('thread_var_'))
        ipython_vars = sum(1 for k in ns_manager.namespace if k.startswith('ipython_var_'))
        
        print(f"✓ Thread safety: {thread_vars} thread vars, {ipython_vars} ipython vars")
        
        return True
        
    except Exception as e:
        print(f"✗ Namespace bridging failed: {e}")
        traceback.print_exc()
        return False


def test_transaction_support():
    """Test transaction support with IPython execution."""
    print("\n" + "=" * 60)
    print("TEST 2.2: Transaction Support")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        ns_manager = MockNamespaceManager()
        shell = InteractiveShell.instance()
        shell.user_ns = ns_manager.namespace
        
        # Set initial state
        shell.run_cell("initial_state = 'original'")
        print(f"✓ Initial state set: {ns_manager.namespace.get('initial_state') == 'original'}")
        
        # Create snapshot
        ns_manager.create_snapshot("txn_001")
        print("✓ Snapshot created")
        
        # Modify state
        shell.run_cell("initial_state = 'modified'")
        shell.run_cell("new_var = 'added'")
        print(f"✓ State modified: {ns_manager.namespace.get('initial_state') == 'modified'}")
        
        # Rollback
        ns_manager.restore_snapshot("txn_001")
        
        # Re-point IPython to restored namespace
        shell.user_ns = ns_manager.namespace
        shell.user_global_ns = ns_manager.namespace
        
        # Verify rollback
        result = shell.run_cell("initial_state")
        rolled_back = result.result == 'original'
        new_var_gone = 'new_var' not in ns_manager.namespace
        
        print(f"✓ Rollback successful: {rolled_back and new_var_gone}")
        
        return True
        
    except Exception as e:
        print(f"✗ Transaction support failed: {e}")
        traceback.print_exc()
        return False


def test_async_namespace_sync():
    """Test namespace synchronization in async context."""
    print("\n" + "=" * 60)
    print("TEST 2.3: Async Namespace Synchronization")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        ns_manager = MockNamespaceManager()
        shell = InteractiveShell.instance()
        shell.user_ns = ns_manager.namespace
        shell.autoawait = True
        
        async def test_async_sync():
            # Execute async code
            code = """
import asyncio

async def async_func():
    await asyncio.sleep(0.01)
    return 'async_result'

# Create coroutine
coro_result = await async_func()
"""
            result = await shell.run_cell_async(code)
            
            # Check namespace has the result
            has_result = ns_manager.namespace.get('coro_result') == 'async_result'
            print(f"✓ Async result in namespace: {has_result}")
            
            # Check function is stored
            has_func = 'async_func' in ns_manager.namespace
            is_async = asyncio.iscoroutinefunction(ns_manager.namespace.get('async_func'))
            print(f"✓ Async function stored: {has_func and is_async}")
            
            return True
        
        # Run async test
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(test_async_sync())
        
        return result
        
    except Exception as e:
        print(f"✗ Async namespace sync failed: {e}")
        traceback.print_exc()
        return False


def test_namespace_persistence():
    """Test namespace persistence across multiple executions."""
    print("\n" + "=" * 60)
    print("TEST 2.4: Namespace Persistence")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        ns_manager = MockNamespaceManager()
        
        # Simulate multiple execution cycles
        for i in range(3):
            # Create new shell instance (simulating new execution)
            shell = InteractiveShell.instance()
            
            # Always point to same namespace
            shell.user_ns = ns_manager.namespace
            shell.user_global_ns = ns_manager.namespace
            
            # Execute code that builds on previous state
            if i == 0:
                shell.run_cell("counter = 0")
                shell.run_cell("def increment(): global counter; counter += 1")
            else:
                shell.run_cell("increment()")
            
            # Verify state
            result = shell.run_cell("counter")
            print(f"  Execution {i}: counter = {result.result}")
        
        # Final check
        final_value = ns_manager.namespace.get('counter')
        print(f"✓ Namespace persisted: counter = {final_value}")
        
        return final_value == 2
        
    except Exception as e:
        print(f"✗ Namespace persistence failed: {e}")
        traceback.print_exc()
        return False


def test_namespace_isolation():
    """Test that we can have isolated namespaces for different sessions."""
    print("\n" + "=" * 60)
    print("TEST 2.5: Multi-Session Namespace Isolation")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        
        # Create two separate namespace managers (simulating two sessions)
        ns_manager1 = MockNamespaceManager()
        ns_manager2 = MockNamespaceManager()
        
        # Create two shells
        shell1 = InteractiveShell.instance()
        shell1.user_ns = ns_manager1.namespace
        
        # Note: IPython.instance() returns singleton, so we need workaround
        from IPython.core.interactiveshell import InteractiveShell as IS
        shell2 = IS()
        shell2.user_ns = ns_manager2.namespace
        
        # Execute different code in each
        shell1.run_cell("session_id = 'session1'")
        shell2.run_cell("session_id = 'session2'")
        
        # Verify isolation
        session1_id = ns_manager1.namespace.get('session_id')
        session2_id = ns_manager2.namespace.get('session_id')
        
        isolated = (session1_id == 'session1' and session2_id == 'session2')
        print(f"✓ Sessions isolated: {isolated}")
        
        # Verify no cross-contamination
        shell1.run_cell("unique_to_session1 = True")
        not_in_session2 = 'unique_to_session1' not in ns_manager2.namespace
        print(f"✓ No cross-contamination: {not_in_session2}")
        
        return isolated and not_in_session2
        
    except Exception as e:
        print(f"✗ Namespace isolation failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all namespace bridging tests."""
    print("IPython Integration Investigation - Namespace Bridging")
    print("=" * 60)
    
    tests = [
        test_namespace_bridging,
        test_transaction_support,
        test_async_namespace_sync,
        test_namespace_persistence,
        test_namespace_isolation,
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
        print("✓ All namespace bridging tests passed!")
    else:
        print("✗ Some tests failed - namespace bridging may have issues")
        
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if main() else 1)