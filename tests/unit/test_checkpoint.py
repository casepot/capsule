"""Unit tests for checkpoint functionality."""

import pytest
import pickle
import gzip
from src.subprocess.checkpoint import Checkpoint, CheckpointManager


@pytest.mark.unit
class TestCheckpoint:
    """Test Checkpoint class."""
    
    def test_checkpoint_creation(self):
        """Test creating a checkpoint."""
        checkpoint = Checkpoint(
            namespace={"x": 42, "y": "hello"},
            function_sources={"my_func": "def my_func(): pass"},
            class_sources={"MyClass": "class MyClass: pass"},
            imports=["import sys", "import os"],
            metadata={"version": "1.0"}
        )
        
        assert checkpoint.namespace["x"] == 42
        assert "my_func" in checkpoint.function_sources
        assert "MyClass" in checkpoint.class_sources
        assert len(checkpoint.imports) == 2
    
    def test_checkpoint_serialization(self):
        """Test serializing checkpoint to bytes."""
        checkpoint = Checkpoint(
            namespace={"x": 42},
            function_sources={},
            class_sources={},
            imports=[],
            metadata={"test": True}
        )
        
        data = checkpoint.to_bytes()
        assert isinstance(data, bytes)
        assert len(data) > 0
        
        # Should be compressed
        assert data[:2] == b'\x1f\x8b'  # gzip magic number
    
    def test_checkpoint_deserialization(self):
        """Test deserializing checkpoint from bytes."""
        original = Checkpoint(
            namespace={"x": 42, "name": "test"},
            function_sources={"foo": "def foo(): return 1"},
            class_sources={},
            imports=["import math"],
            metadata={"timestamp": 123456}
        )
        
        data = original.to_bytes()
        restored = Checkpoint.from_bytes(data)
        
        assert restored.namespace["x"] == 42
        assert restored.namespace["name"] == "test"
        assert restored.function_sources["foo"] == "def foo(): return 1"
        assert restored.imports == ["import math"]
        assert restored.metadata["timestamp"] == 123456
    
    def test_checkpoint_with_complex_types(self):
        """Test checkpoint with complex Python types."""
        import numpy as np
        
        checkpoint = Checkpoint(
            namespace={
                "array": np.array([1, 2, 3]),
                "func": lambda x: x * 2,
                "dict": {"nested": {"deep": "value"}}
            },
            function_sources={},
            class_sources={},
            imports=[],
            metadata={}
        )
        
        data = checkpoint.to_bytes()
        restored = Checkpoint.from_bytes(data)
        
        assert restored.namespace["dict"]["nested"]["deep"] == "value"
        # Note: lambdas and numpy arrays need dill for proper serialization


@pytest.mark.unit
class TestCheckpointManager:
    """Test CheckpointManager functionality."""
    
    def test_manager_creation(self):
        """Test creating a checkpoint manager."""
        manager = CheckpointManager()
        assert manager.namespace_manager is not None
    
    def test_create_checkpoint(self):
        """Test creating checkpoint from current state."""
        manager = CheckpointManager()
        
        # Set up some state
        manager.namespace_manager.set("x", 100)
        manager.namespace_manager.set("y", "test")
        manager.namespace_manager.track_function("my_func", "def my_func(): pass")
        
        checkpoint = manager.create_checkpoint()
        
        assert checkpoint.namespace["x"] == 100
        assert checkpoint.namespace["y"] == "test"
        assert "my_func" in checkpoint.function_sources
    
    def test_restore_checkpoint(self):
        """Test restoring from checkpoint."""
        manager = CheckpointManager()
        
        # Create initial state
        manager.namespace_manager.set("x", 100)
        checkpoint = manager.create_checkpoint()
        
        # Modify state
        manager.namespace_manager.set("x", 200)
        manager.namespace_manager.set("z", "new")
        
        # Restore checkpoint
        manager.restore_checkpoint(checkpoint)
        
        assert manager.namespace_manager.get("x") == 100
        assert not manager.namespace_manager.exists("z")
    
    def test_checkpoint_metadata(self):
        """Test checkpoint metadata generation."""
        manager = CheckpointManager()
        manager.namespace_manager.set("test", True)
        
        checkpoint = manager.create_checkpoint(
            metadata={"user": "test_user", "description": "Test checkpoint"}
        )
        
        assert "timestamp" in checkpoint.metadata
        assert checkpoint.metadata["user"] == "test_user"
        assert checkpoint.metadata["description"] == "Test checkpoint"