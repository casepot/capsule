from __future__ import annotations

import ast
import base64
import gzip
import pickle
from dataclasses import dataclass
from typing import Any, Dict, Optional

import dill
import structlog

from .namespace import NamespaceManager

logger = structlog.get_logger()


@dataclass
class Checkpoint:
    """Represents a complete session checkpoint."""

    namespace: Dict[str, Any]
    function_sources: Dict[str, str]
    class_sources: Dict[str, str]
    imports: list[str]
    metadata: Dict[str, Any]

    def to_bytes(self) -> bytes:
        """Serialize checkpoint to bytes.

        Returns:
            Compressed checkpoint data
        """
        # Create checkpoint dictionary
        checkpoint_dict = {
            "version": "1.0",
            "namespace": self._serialize_namespace(),
            "function_sources": self.function_sources,
            "class_sources": self.class_sources,
            "imports": self.imports,
            "metadata": self.metadata,
        }

        # Serialize with dill (handles more types than pickle)
        serialized = dill.dumps(checkpoint_dict, protocol=pickle.HIGHEST_PROTOCOL)

        # Compress with gzip
        compressed = gzip.compress(serialized, compresslevel=6)

        return compressed

    @classmethod
    def from_bytes(cls, data: bytes) -> Checkpoint:
        """Deserialize checkpoint from bytes.

        Args:
            data: Compressed checkpoint data

        Returns:
            Checkpoint instance
        """
        # Decompress
        decompressed = gzip.decompress(data)

        # Deserialize
        checkpoint_dict = dill.loads(decompressed)

        # Validate version
        version = checkpoint_dict.get("version")
        if version != "1.0":
            raise ValueError(f"Unsupported checkpoint version: {version}")

        # Create checkpoint
        return cls(
            namespace=cls._deserialize_namespace(checkpoint_dict["namespace"]),
            function_sources=checkpoint_dict["function_sources"],
            class_sources=checkpoint_dict["class_sources"],
            imports=checkpoint_dict["imports"],
            metadata=checkpoint_dict["metadata"],
        )

    def _serialize_namespace(self) -> Dict[str, Any]:
        """Serialize namespace for checkpointing.

        Returns:
            Serialized namespace
        """
        serialized = {}

        for key, value in self.namespace.items():
            # Skip built-in attributes
            if key.startswith("__") and key.endswith("__"):
                if key not in ["__name__", "__doc__"]:
                    continue

            try:
                # Try to serialize with dill
                serialized[key] = {
                    "type": "value",
                    "data": base64.b64encode(dill.dumps(value)).decode("ascii"),
                }
            except Exception:
                # Fall back to storing type info
                serialized[key] = {
                    "type": "reference",
                    "class": type(value).__name__,
                    "module": type(value).__module__,
                    "repr": repr(value)[:1000],  # Truncate long reprs
                }

        return serialized

    @staticmethod
    def _deserialize_namespace(serialized: Dict[str, Any]) -> Dict[str, Any]:
        """Deserialize namespace from checkpoint.

        Args:
            serialized: Serialized namespace

        Returns:
            Restored namespace
        """
        namespace = {}

        for key, item in serialized.items():
            if item["type"] == "value":
                # Deserialize value
                try:
                    data = base64.b64decode(item["data"])
                    namespace[key] = dill.loads(data)
                except Exception as e:
                    logger.warning(
                        "Failed to restore value",
                        key=key,
                        error=str(e),
                    )
            elif item["type"] == "reference":
                # Can't restore, log warning
                logger.warning(
                    "Cannot restore non-serializable object",
                    key=key,
                    class_name=item["class"],
                )

        return namespace

    def get_size(self) -> int:
        """Get checkpoint size in bytes.

        Returns:
            Size in bytes
        """
        return len(self.to_bytes())

    def get_info(self) -> Dict[str, Any]:
        """Get checkpoint information.

        Returns:
            Checkpoint statistics
        """
        return {
            "namespace_size": len(self.namespace),
            "function_count": len(self.function_sources),
            "class_count": len(self.class_sources),
            "import_count": len(self.imports),
            "checkpoint_size": self.get_size(),
            "metadata": self.metadata,
        }


class CheckpointManager:
    """Manages checkpoint creation and restoration."""

    def __init__(self, namespace_manager: NamespaceManager) -> None:
        self._namespace_manager = namespace_manager
        self._checkpoints: Dict[str, Checkpoint] = {}

    def create_checkpoint(
        self,
        checkpoint_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Checkpoint:
        """Create a checkpoint of current state.

        Args:
            checkpoint_id: Optional checkpoint ID for storage
            metadata: Optional metadata to include

        Returns:
            Created checkpoint
        """
        import time
        import uuid

        if checkpoint_id is None:
            checkpoint_id = str(uuid.uuid4())

        if metadata is None:
            metadata = {}

        # Add timestamp
        metadata["timestamp"] = time.time()
        metadata["checkpoint_id"] = checkpoint_id

        # Create checkpoint
        checkpoint = Checkpoint(
            namespace=dict(self._namespace_manager.namespace),
            function_sources=dict(self._namespace_manager.function_sources),
            class_sources=dict(self._namespace_manager.class_sources),
            imports=list(self._namespace_manager.imports),
            metadata=metadata,
        )

        # Store if ID provided
        if checkpoint_id:
            self._checkpoints[checkpoint_id] = checkpoint

        logger.info(
            "Created checkpoint",
            checkpoint_id=checkpoint_id,
            size=checkpoint.get_size(),
        )

        return checkpoint

    def restore_checkpoint(
        self,
        checkpoint: Checkpoint,
        clear_existing: bool = True,
    ) -> None:
        """Restore state from checkpoint.

        Args:
            checkpoint: Checkpoint to restore
            clear_existing: Whether to clear existing namespace
        """
        if clear_existing:
            self._namespace_manager.clear()

        # Restore imports first
        for import_stmt in checkpoint.imports:
            try:
                exec(import_stmt, self._namespace_manager.namespace)
            except Exception as e:
                logger.warning(
                    "Failed to restore import",
                    import_stmt=import_stmt,
                    error=str(e),
                )

        # Restore classes
        for class_name, class_source in checkpoint.class_sources.items():
            try:
                exec(class_source, self._namespace_manager.namespace)
                logger.debug("Restored class", name=class_name)
            except Exception as e:
                logger.warning(
                    "Failed to restore class",
                    name=class_name,
                    error=str(e),
                )

        # Restore functions
        for func_name, func_source in checkpoint.function_sources.items():
            try:
                exec(func_source, self._namespace_manager.namespace)
                logger.debug("Restored function", name=func_name)
            except Exception as e:
                logger.warning(
                    "Failed to restore function",
                    name=func_name,
                    error=str(e),
                )

        # Restore namespace values
        for key, value in checkpoint.namespace.items():
            # Skip if already restored (function/class)
            if key not in self._namespace_manager.namespace:
                self._namespace_manager.namespace[key] = value

        # Update tracked sources
        self._namespace_manager.update_function_sources(checkpoint.function_sources)
        self._namespace_manager.update_class_sources(checkpoint.class_sources)
        self._namespace_manager.add_imports(checkpoint.imports)

        logger.info(
            "Restored checkpoint",
            namespace_size=len(self._namespace_manager.namespace),
        )

    def save_checkpoint(self, filepath: str) -> None:
        """Save checkpoint to file.

        Args:
            filepath: Path to save checkpoint
        """
        checkpoint = self.create_checkpoint()
        data = checkpoint.to_bytes()

        with open(filepath, "wb") as f:
            f.write(data)

        logger.info("Saved checkpoint to file", path=filepath, size=len(data))

    def load_checkpoint(self, filepath: str) -> Checkpoint:
        """Load checkpoint from file.

        Args:
            filepath: Path to checkpoint file

        Returns:
            Loaded checkpoint
        """
        with open(filepath, "rb") as f:
            data = f.read()

        checkpoint = Checkpoint.from_bytes(data)

        logger.info(
            "Loaded checkpoint from file",
            path=filepath,
            size=len(data),
        )

        return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Get stored checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint identifier

        Returns:
            Checkpoint if found, None otherwise
        """
        return self._checkpoints.get(checkpoint_id)

    def list_checkpoints(self) -> list[str]:
        """List all stored checkpoint IDs.

        Returns:
            List of checkpoint IDs
        """
        return list(self._checkpoints.keys())

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete stored checkpoint.

        Args:
            checkpoint_id: Checkpoint identifier

        Returns:
            True if deleted, False if not found
        """
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
            logger.info("Deleted checkpoint", checkpoint_id=checkpoint_id)
            return True
        return False

    def validate_checkpoint(self, checkpoint: Checkpoint) -> Dict[str, Any]:
        """Validate checkpoint integrity.

        Args:
            checkpoint: Checkpoint to validate

        Returns:
            Validation results
        """
        issues = []

        # Check for missing imports
        for import_stmt in checkpoint.imports:
            try:
                # Try to compile import
                compile(import_stmt, "<checkpoint>", "exec")
            except SyntaxError:
                issues.append(f"Invalid import: {import_stmt}")

        # Check function sources
        for func_name, func_source in checkpoint.function_sources.items():
            try:
                ast.parse(func_source)
            except SyntaxError as e:
                issues.append(f"Invalid function source for {func_name}: {e}")

        # Check class sources
        for class_name, class_source in checkpoint.class_sources.items():
            try:
                ast.parse(class_source)
            except SyntaxError as e:
                issues.append(f"Invalid class source for {class_name}: {e}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "info": checkpoint.get_info(),
        }
