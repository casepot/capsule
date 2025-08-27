"""Unit tests for checkpoint functionality."""

import pytest
import pickle
import dill
from unittest.mock import Mock, MagicMock
from src.subprocess.checkpoint import Checkpoint, CheckpointManager
from src.subprocess.namespace import NamespaceManager


@pytest.mark.unit
class TestCheckpoint:
    """Test Checkpoint class."""
    
    def test_checkpoint_creation(self):
        """Test creating a checkpoint."""
        checkpoint = Checkpoint(
            namespace={"x": 42, "y": "test"},
            function_sources={"func1": "def func1(): pass"},
            class_sources={"Class1": "class Class1: pass"},
            imports=["import math", "from typing import List"],
            metadata={"timestamp": 12345}
        )
        
        assert checkpoint.namespace == {"x": 42, "y": "test"}
        assert checkpoint.function_sources == {"func1": "def func1(): pass"}
        assert checkpoint.class_sources == {"Class1": "class Class1: pass"}
        assert checkpoint.imports == ["import math", "from typing import List"]
        assert checkpoint.metadata == {"timestamp": 12345}
    
    def test_checkpoint_serialization(self):
        """Test serializing checkpoint to bytes."""
        checkpoint = Checkpoint(
            namespace={"x": 42},
            function_sources={},
            class_sources={},
            imports=[],
            metadata={"test": True}
        )
        
        # Serialize
        data = checkpoint.to_bytes()
        assert isinstance(data, bytes)
        assert len(data) > 0
    
    def test_checkpoint_deserialization(self):
        """Test deserializing checkpoint from bytes."""
        original = Checkpoint(
            namespace={"x": 42, "name": "test"},
            function_sources={"greet": "def greet(): return 'hello'"},
            class_sources={},
            imports=["import sys"],
            metadata={"version": 1}
        )
        
        # Serialize and deserialize
        data = original.to_bytes()
        restored = Checkpoint.from_bytes(data)
        
        # Verify restoration
        assert restored.namespace == original.namespace
        assert restored.function_sources == original.function_sources
        assert restored.class_sources == original.class_sources
        assert restored.imports == original.imports
        assert restored.metadata == original.metadata
    
    def test_checkpoint_with_complex_types(self):
        """Test checkpoint with complex Python types."""
        # Create complex objects
        def sample_func(x):
            return x * 2
        
        class SampleClass:
            def __init__(self):
                self.value = 100
        
        checkpoint = Checkpoint(
            namespace={
                "func": sample_func,
                "cls": SampleClass,
                "instance": SampleClass(),
                "list": [1, 2, 3],
                "dict": {"nested": {"key": "value"}}
            },
            function_sources={},
            class_sources={},
            imports=[],
            metadata={}
        )
        
        # Should be able to serialize complex types with dill
        data = checkpoint.to_bytes()
        assert isinstance(data, bytes)
        
        # Note: Deserialization of functions/classes requires special handling
        # which is implemented in _serialize_namespace and _deserialize_namespace


@pytest.mark.unit
class TestCheckpointManager:
    """Test CheckpointManager functionality."""
    
    def test_manager_creation(self):
        """Test creating a checkpoint manager."""
        namespace_manager = Mock(spec=NamespaceManager)
        manager = CheckpointManager(namespace_manager)
        
        assert manager._namespace_manager is namespace_manager
        assert manager._checkpoints == {}
    
    def test_create_checkpoint(self):
        """Test creating a checkpoint through manager."""
        # Mock namespace manager
        namespace_manager = Mock(spec=NamespaceManager)
        namespace_manager.namespace = {"x": 42}
        namespace_manager.function_sources = {}
        namespace_manager.class_sources = {}
        namespace_manager.imports = []
        
        manager = CheckpointManager(namespace_manager)
        
        # Create checkpoint
        checkpoint = manager.create_checkpoint(
            checkpoint_id="test1",
            metadata={"user": "test"}
        )
        
        assert isinstance(checkpoint, Checkpoint)
        assert checkpoint.namespace == {"x": 42}
        # Metadata will include auto-added fields like timestamp and checkpoint_id
        assert checkpoint.metadata["user"] == "test"
        assert checkpoint.metadata["checkpoint_id"] == "test1"
        assert "timestamp" in checkpoint.metadata
        
        # Should be stored
        assert "test1" in manager._checkpoints
        assert manager._checkpoints["test1"] is checkpoint
    
    def test_restore_checkpoint(self):
        """Test restoring a checkpoint."""
        # Mock namespace manager with a namespace dict
        namespace_manager = Mock(spec=NamespaceManager)
        namespace_manager.namespace = {}
        manager = CheckpointManager(namespace_manager)
        
        # Create and store checkpoint
        checkpoint = Checkpoint(
            namespace={"x": 100, "y": "restored"},
            function_sources={"func": "def func(): pass"},
            class_sources={"Cls": "class Cls: pass"},
            imports=["import os"],
            metadata={}
        )
        manager._checkpoints["test1"] = checkpoint
        
        # Restore checkpoint - pass the checkpoint object, not the ID
        manager.restore_checkpoint(checkpoint)
        
        # Verify clear was called (restore calls clear by default)
        namespace_manager.clear.assert_called_once()
    
    def test_get_checkpoint(self):
        """Test retrieving checkpoint by ID."""
        namespace_manager = Mock(spec=NamespaceManager)
        manager = CheckpointManager(namespace_manager)
        
        # Store a checkpoint
        checkpoint = Checkpoint(
            namespace={"test": "data"},
            function_sources={},
            class_sources={},
            imports=[],
            metadata={}
        )
        manager._checkpoints["test1"] = checkpoint
        
        # Retrieve it
        retrieved = manager.get_checkpoint("test1")
        assert retrieved is checkpoint
        
        # Try non-existent
        assert manager.get_checkpoint("nonexistent") is None
    
    def test_checkpoint_metadata(self):
        """Test checkpoint metadata handling."""
        namespace_manager = Mock(spec=NamespaceManager)
        namespace_manager.namespace = {}
        namespace_manager.function_sources = {}
        namespace_manager.class_sources = {}
        namespace_manager.imports = []
        
        manager = CheckpointManager(namespace_manager)
        
        # Create checkpoint with metadata
        import time
        metadata = {
            "description": "Test checkpoint",
            "user": "pytest"
        }
        
        checkpoint = manager.create_checkpoint(
            checkpoint_id="meta_test",
            metadata=metadata
        )
        
        # Check user-provided metadata is preserved
        assert checkpoint.metadata["description"] == "Test checkpoint"
        assert checkpoint.metadata["user"] == "pytest"
        # Auto-added metadata
        assert checkpoint.metadata["checkpoint_id"] == "meta_test"
        assert "timestamp" in checkpoint.metadata