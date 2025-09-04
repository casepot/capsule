"""Unit tests for namespace merge-only policy implementation.

This test file validates the critical namespace management changes that
prevent KeyError failures and preserve engine internals.
"""

import pytest
import threading
import time
from typing import Dict, Any

from src.subprocess.namespace import NamespaceManager
from src.subprocess.worker import SubprocessWorker
from src.protocol.transport import MessageTransport
from unittest.mock import Mock


class TestNamespaceMergePolicy:
    """Test namespace merge-only policy implementation."""
    
    def test_namespace_never_replaced(self):
        """CRITICAL: Test that namespace is never replaced, only updated."""
        # This is the most critical test - prevents KeyError
        manager = NamespaceManager()
        
        # Get initial namespace reference
        initial_id = id(manager._namespace)
        
        # Various update operations
        manager.update_namespace({"x": 1})
        assert id(manager._namespace) == initial_id, "Namespace was replaced after update_namespace"
        
        manager.update_namespace({"y": 2})
        assert id(manager._namespace) == initial_id, "Namespace was replaced after second update"
        
        # Clear should also preserve the namespace object
        manager.clear()
        assert id(manager._namespace) == initial_id, "Namespace was replaced after clear"
        
        # Execute should not replace namespace
        manager.execute("z = 3")
        assert id(manager._namespace) == initial_id, "Namespace was replaced after execute"
        
        # Namespace object must be the same throughout
        assert initial_id == id(manager._namespace), "Namespace object identity was not preserved"
    
    def test_engine_internals_initialized(self):
        """Test that engine internals are properly initialized."""
        manager = NamespaceManager()
        
        # Check all engine internals exist
        for key in NamespaceManager.ENGINE_INTERNALS:
            assert key in manager._namespace, f"Engine internal '{key}' not initialized"
        
        # Check proper types
        assert isinstance(manager._namespace['Out'], dict), "Out should be a dict"
        assert isinstance(manager._namespace['_oh'], dict), "_oh should be a dict"
        assert isinstance(manager._namespace['In'], list), "In should be a list"
        assert isinstance(manager._namespace['_ih'], list), "_ih should be a list"
        
        # Check other internals are None initially
        assert manager._namespace['_'] is None, "_ should be None initially"
        assert manager._namespace['__'] is None, "__ should be None initially"
        assert manager._namespace['___'] is None, "___ should be None initially"
    
    def test_engine_internals_preserved(self):
        """Test that engine internals are protected from user context."""
        manager = NamespaceManager()
        
        # Try to overwrite engine internal from user context
        manager.update_namespace({'_': 'user_value'}, source_context='user')
        
        # Should not be changed (protected)
        assert manager._namespace['_'] is None, "Engine internal was modified by user context"
        
        # But engine context can update it
        manager.update_namespace({'_': 'engine_value'}, source_context='engine')
        assert manager._namespace['_'] == 'engine_value', "Engine context should be able to update internals"
        
        # Test all internals are protected
        for key in NamespaceManager.ENGINE_INTERNALS:
            manager.update_namespace({key: 'user_attempt'}, source_context='user')
            assert manager._namespace[key] != 'user_attempt', f"Protected key {key} was modified by user"
    
    def test_merge_strategies(self):
        """Test different merge strategies."""
        manager = NamespaceManager()
        
        # Test overwrite strategy (default)
        manager.update_namespace({"x": 1})
        manager.update_namespace({"x": 2}, merge_strategy="overwrite")
        assert manager._namespace["x"] == 2, "Overwrite strategy failed"
        
        # Test preserve strategy
        manager.update_namespace({"x": 3}, merge_strategy="preserve")
        assert manager._namespace["x"] == 2, "Preserve strategy should not change existing value"
        
        # Test preserve on new key
        manager.update_namespace({"new_key": "value"}, merge_strategy="preserve")
        assert manager._namespace["new_key"] == "value", "Preserve should add new keys"
        
        # Test smart strategy with None
        manager.update_namespace({"x": None}, merge_strategy="smart")
        assert manager._namespace["x"] == 2, "Smart strategy should not overwrite with None"
        
        # Test smart with empty containers
        manager.update_namespace({"list_key": [1, 2, 3]})
        manager.update_namespace({"list_key": []}, merge_strategy="smart")
        assert manager._namespace["list_key"] == [1, 2, 3], "Smart should not overwrite with empty list"
        
        # Test smart with actual change
        manager.update_namespace({"x": 42}, merge_strategy="smart")
        assert manager._namespace["x"] == 42, "Smart should update when value changes"
    
    def test_result_history_tracking(self):
        """Test that result history (_, __, ___) is tracked correctly."""
        manager = NamespaceManager()
        
        # Initially all should be None
        assert manager._namespace['_'] is None
        assert manager._namespace['__'] is None
        assert manager._namespace['___'] is None
        
        # Track first result
        manager._update_result_history(1)
        assert manager._namespace['_'] == 1
        assert manager._namespace['__'] is None
        assert manager._namespace['___'] is None
        
        # Track second result
        manager._update_result_history(2)
        assert manager._namespace['_'] == 2
        assert manager._namespace['__'] == 1
        assert manager._namespace['___'] is None
        
        # Track third result
        manager._update_result_history(3)
        assert manager._namespace['_'] == 3
        assert manager._namespace['__'] == 2
        assert manager._namespace['___'] == 1
        
        # Track fourth result (should shift all)
        manager._update_result_history(4)
        assert manager._namespace['_'] == 4
        assert manager._namespace['__'] == 3
        assert manager._namespace['___'] == 2
        
        # None should not update history
        manager._update_result_history(None)
        assert manager._namespace['_'] == 4  # Unchanged
    
    def test_out_dict_updates(self):
        """Test that Out dict is updated with results."""
        manager = NamespaceManager()
        
        # Out should be initialized as empty dict
        assert manager._namespace['Out'] == {}
        
        # Update result history
        manager._update_result_history(42)
        assert manager._namespace['Out'][0] == 42, "Out[0] should contain first result"
        
        manager._update_result_history("hello")
        assert manager._namespace['Out'][1] == "hello", "Out[1] should contain second result"
        
        # Check order is preserved
        assert len(manager._namespace['Out']) == 2
        assert list(manager._namespace['Out'].values()) == [42, "hello"]
    
    def test_thread_safe_access(self):
        """Test thread-safe namespace access."""
        manager = NamespaceManager()
        
        results = []
        errors = []
        
        def worker(n):
            try:
                for i in range(100):
                    manager.update_namespace({f"thread_{n}_{i}": i})
                    time.sleep(0.0001)  # Small delay to increase concurrency
                results.append(n)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = []
        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # No errors should occur
        assert len(errors) == 0, f"Thread errors occurred: {errors}"
        assert len(results) == 10, "Not all threads completed"
        
        # All updates should be present
        for n in range(10):
            for i in range(100):
                assert f"thread_{n}_{i}" in manager._namespace, f"Missing thread_{n}_{i}"
                assert manager._namespace[f"thread_{n}_{i}"] == i, f"Wrong value for thread_{n}_{i}"
    
    def test_clear_preserves_internals(self):
        """Test that clear() preserves engine internals."""
        manager = NamespaceManager()
        
        # Set some engine internals
        manager.update_namespace({'_': 42}, source_context='engine')
        manager.update_namespace({'__': 'previous'}, source_context='engine')
        manager._namespace['Out'][0] = 'result'
        
        # Add user data
        manager.update_namespace({'user_var': 'data'})
        
        # Clear namespace
        manager.clear()
        
        # Engine internals should be preserved
        assert manager._namespace['_'] == 42, "_ was not preserved"
        assert manager._namespace['__'] == 'previous', "__ was not preserved"
        assert manager._namespace['Out'][0] == 'result', "Out history was not preserved"
        
        # User data should be cleared
        assert 'user_var' not in manager._namespace, "User data was not cleared"
        
        # Builtins should be restored
        assert '__builtins__' in manager._namespace, "Builtins not restored"
        assert '__name__' in manager._namespace, "Name not restored"
    
    def test_worker_namespace_setup(self):
        """Test SubprocessWorker namespace setup follows merge policy."""
        transport = Mock(spec=MessageTransport)
        worker = SubprocessWorker(transport, "test-session")
        
        # Get initial namespace reference
        initial_id = id(worker._namespace)
        
        # Setup should have been called in __init__
        # Check internals are initialized
        for key in SubprocessWorker.ENGINE_INTERNALS:
            assert key in worker._namespace, f"Worker missing engine internal '{key}'"
        
        # Call setup again - should not replace namespace
        worker._setup_namespace()
        assert id(worker._namespace) == initial_id, "Worker namespace was replaced on re-setup"
        
        # Check types are correct
        assert isinstance(worker._namespace['Out'], dict), "Worker Out should be dict"
        assert isinstance(worker._namespace['In'], list), "Worker In should be list"
    
    def test_update_returns_changes(self):
        """Test that update_namespace returns only actual changes."""
        manager = NamespaceManager()
        
        # First update should return all changes
        changes = manager.update_namespace({"a": 1, "b": 2})
        assert changes == {"a": 1, "b": 2}, "Should return all new values"
        
        # Update with same values using smart strategy should return empty
        changes = manager.update_namespace({"a": 1}, merge_strategy="smart")
        assert changes == {}, "Should return empty when no actual change with smart strategy"
        
        # Update with one change should return all updated with overwrite strategy
        changes = manager.update_namespace({"a": 1, "b": 3})
        assert "b" in changes and changes["b"] == 3, "Should return changed value"
        
        # Protected keys should not appear in changes
        changes = manager.update_namespace({"_": "attempt"}, source_context="user")
        assert "_" not in changes, "Protected key should not appear in changes"


class TestNamespaceIntegration:
    """Integration tests for namespace with other components."""
    
    def test_namespace_with_transactions(self):
        """Test namespace works correctly with transaction support."""
        manager = NamespaceManager()
        
        # Set initial state
        manager.update_namespace({"x": 1})
        
        # Create snapshot
        manager.create_snapshot("test-txn")
        
        # Modify namespace
        manager.update_namespace({"x": 2, "y": 3})
        assert manager._namespace["x"] == 2
        
        # Restore snapshot
        manager.restore_snapshot("test-txn")
        
        # Should be back to original state
        assert manager._namespace["x"] == 1
        assert "y" not in manager._namespace
        
        # Engine internals should still be present
        for key in NamespaceManager.ENGINE_INTERNALS:
            assert key in manager._namespace, f"Lost engine internal {key} after restore"
    
    def test_execute_preserves_namespace(self):
        """Test that execute() method preserves namespace."""
        manager = NamespaceManager()
        
        initial_id = id(manager._namespace)
        
        # Execute some code
        manager.execute("test_var = 42")
        
        # Namespace should not be replaced
        assert id(manager._namespace) == initial_id, "Execute replaced namespace"
        assert manager._namespace["test_var"] == 42, "Variable not set"
        
        # Execute expression
        result = manager.execute("test_var * 2")
        assert result == 84, "Expression result incorrect"
        assert id(manager._namespace) == initial_id, "Execute expression replaced namespace"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-x"])