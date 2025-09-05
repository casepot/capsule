from __future__ import annotations

import ast
import copy
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

import structlog

from ..protocol.messages import TransactionPolicy
from .constants import ENGINE_INTERNALS

logger = structlog.get_logger()


class NamespaceManager:
    """Manages Python namespace with transaction support."""

    # Engine internals imported from constants module
    # See constants.py for the complete list and documentation

    def __init__(self) -> None:
        self._namespace: Dict[str, Any] = {}
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._function_sources: Dict[str, str] = {}
        self._class_sources: Dict[str, str] = {}
        self._imports: list[str] = []

        # Initialize with builtins
        self._setup_namespace()

    def _setup_namespace(self) -> None:
        """Setup the initial namespace.

        CRITICAL: Never replace namespace, always merge/update to preserve
        engine internals and prevent KeyError failures.
        """
        import builtins

        # CRITICAL: Never replace, always update (spec line 22)
        # Start with required built-ins
        self._namespace.update(
            {
                "__name__": "__main__",
                "__doc__": None,
                "__package__": None,
                "__loader__": None,
                "__spec__": None,
                "__annotations__": {},
                "__builtins__": builtins,
            }
        )

        # Initialize engine internals with proper defaults
        for key in ENGINE_INTERNALS:
            if key not in self._namespace:
                if key in ["Out", "_oh"]:
                    self._namespace[key] = {}
                elif key in ["In", "_ih"]:
                    self._namespace[key] = []
                else:
                    self._namespace[key] = None

    @property
    def namespace(self) -> Dict[str, Any]:
        """Get the current namespace."""
        return self._namespace

    def update_namespace(
        self,
        updates: Dict[str, Any],
        source_context: str = "user",
        merge_strategy: str = "overwrite",
    ) -> Dict[str, Any]:
        """Update namespace with merge-only policy.

        CRITICAL: This method MERGES updates, never replaces the namespace.

        Args:
            updates: Dictionary of updates to merge
            source_context: Source of updates ("user", "engine", "thread")
            merge_strategy: How to merge ("overwrite", "preserve", "smart")

        Returns:
            Dict of actual changes made
        """
        if not updates:
            return {}

        changes: Dict[str, Any] = {}

        for key, value in updates.items():
            # Skip protected keys unless from engine context
            if key in ENGINE_INTERNALS and source_context != "engine":
                # TODO: Use structured logging fields instead of f-strings for machine-parseable logs
                # e.g., logger.debug("Skipping protected key", key=key, source=source_context)
                logger.debug(f"Skipping protected key {key} from {source_context}")
                continue

            # Check if value should be updated based on strategy
            old_value = self._namespace.get(key)

            should_update = False
            if merge_strategy == "overwrite":
                should_update = True
            elif merge_strategy == "preserve":
                should_update = key not in self._namespace
            elif merge_strategy == "smart":
                should_update = self._should_update_smart(key, value, old_value)
            else:
                should_update = True

            if should_update:
                # Special handling for _ to maintain history
                if key == "_":
                    # Let _update_result_history handle the update and shifting
                    self._update_result_history(value)
                    changes[key] = value
                else:
                    # CRITICAL: Use item assignment, not replace
                    self._namespace[key] = value
                    changes[key] = value

        return changes

    def _update_result_history(self, result: Any) -> None:
        """Update result history (_, __, ___).

        Maintains IPython-compatible result tracking.
        """
        if result is None:
            return

        # Shift history
        if "_" in self._namespace and self._namespace["_"] is not None:
            if "__" in self._namespace and self._namespace["__"] is not None:
                self._namespace["___"] = self._namespace["__"]
            self._namespace["__"] = self._namespace["_"]

        # Set new result
        self._namespace["_"] = result

        # Update Out dict if it exists
        if "Out" in self._namespace and isinstance(self._namespace["Out"], dict):
            exec_num = len(self._namespace["Out"])
            self._namespace["Out"][exec_num] = result

    def record_expression_result(self, result: Any) -> None:
        """Record an expression result (not an assignment).

        This method should be called by the executor when evaluating
        an expression that produces a result to display.

        Args:
            result: The expression result to record
        """
        if result is not None:
            self.update_namespace({"_": result}, source_context="engine")

    @property
    def function_sources(self) -> Dict[str, str]:
        """Get tracked function sources."""
        return self._function_sources

    @property
    def class_sources(self) -> Dict[str, str]:
        """Get tracked class sources."""
        return self._class_sources

    @property
    def imports(self) -> list[str]:
        """Get tracked imports."""
        return self._imports

    def create_snapshot(self, transaction_id: str) -> None:
        """Create a snapshot of the current namespace.

        Args:
            transaction_id: Unique transaction identifier
        """
        try:
            # Deep copy the namespace
            # Note: Some objects may not be deep-copyable
            snapshot: Dict[str, Any] = {}

            for key, value in self._namespace.items():
                try:
                    # Try to deep copy
                    snapshot[key] = copy.deepcopy(value)
                except Exception:
                    # Fall back to reference for non-copyable objects
                    snapshot[key] = value

            self._snapshots[transaction_id] = snapshot

            logger.debug(
                "Created snapshot",
                transaction_id=transaction_id,
                namespace_size=len(snapshot),
            )

        except Exception as e:
            logger.error("Failed to create snapshot", error=str(e))
            raise

    def restore_snapshot(self, transaction_id: str) -> None:
        """Restore namespace from a snapshot.

        Args:
            transaction_id: Transaction identifier to restore

        Raises:
            KeyError: If transaction_id not found
        """
        if transaction_id not in self._snapshots:
            raise KeyError(f"Transaction {transaction_id} not found")

        snapshot = self._snapshots[transaction_id]

        # Clear current namespace (except builtins)
        builtins = self._namespace.get("__builtins__")
        self._namespace.clear()

        # Restore from snapshot
        self._namespace.update(snapshot)

        # Ensure builtins are preserved
        if builtins:
            self._namespace["__builtins__"] = builtins

        logger.debug(
            "Restored snapshot",
            transaction_id=transaction_id,
            namespace_size=len(self._namespace),
        )

    def delete_snapshot(self, transaction_id: str) -> None:
        """Delete a snapshot.

        Args:
            transaction_id: Transaction identifier to delete
        """
        if transaction_id in self._snapshots:
            del self._snapshots[transaction_id]
            logger.debug("Deleted snapshot", transaction_id=transaction_id)

    @contextmanager
    def transaction(
        self,
        transaction_id: str,
        policy: TransactionPolicy = TransactionPolicy.COMMIT_ALWAYS,
    ) -> Iterator[None]:
        """Execute code within a transaction context.

        Args:
            transaction_id: Unique transaction identifier
            policy: Transaction commit/rollback policy

        Yields:
            None
        """
        # Create snapshot if needed
        if policy != TransactionPolicy.COMMIT_ALWAYS:
            self.create_snapshot(transaction_id)

        try:
            yield

            # Handle successful execution
            if policy == TransactionPolicy.ROLLBACK_ALWAYS:
                self.restore_snapshot(transaction_id)

            # Clean up snapshot if not needed
            if transaction_id in self._snapshots:
                self.delete_snapshot(transaction_id)

        except Exception:
            # Handle failed execution
            if policy == TransactionPolicy.ROLLBACK_ON_FAILURE:
                if transaction_id in self._snapshots:
                    self.restore_snapshot(transaction_id)

            # Clean up snapshot
            if transaction_id in self._snapshots:
                self.delete_snapshot(transaction_id)

            raise

    def track_sources(self, code: str) -> None:
        """Track function and class sources from code.

        Args:
            code: Python code to analyze
        """
        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Capture function source
                    self._function_sources[node.name] = ast.unparse(node)

                elif isinstance(node, ast.AsyncFunctionDef):
                    # Capture async function source
                    self._function_sources[node.name] = ast.unparse(node)

                elif isinstance(node, ast.ClassDef):
                    # Capture class source
                    self._class_sources[node.name] = ast.unparse(node)

        except Exception as e:
            logger.error("Failed to track sources", error=str(e))

    def track_imports(self, code: str) -> None:
        """Track import statements from code.

        Args:
            code: Python code to analyze
        """
        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    # Track regular imports
                    import_str = ast.unparse(node)
                    if import_str not in self._imports:
                        self._imports.append(import_str)

                elif isinstance(node, ast.ImportFrom):
                    # Track from imports
                    import_str = ast.unparse(node)
                    if import_str not in self._imports:
                        self._imports.append(import_str)

        except Exception as e:
            logger.error("Failed to track imports", error=str(e))

    def execute(
        self,
        code: str,
        track_sources: bool = True,
        transaction_id: Optional[str] = None,
        policy: TransactionPolicy = TransactionPolicy.COMMIT_ALWAYS,
    ) -> Any:
        """Execute code in the namespace with optional transaction support.

        Args:
            code: Python code to execute
            track_sources: Whether to track function/class sources
            transaction_id: Optional transaction ID
            policy: Transaction policy

        Returns:
            Execution result if code is an expression

        Raises:
            Exception: Any exception from code execution
        """
        # Track sources and imports if requested
        if track_sources:
            self.track_sources(code)
            self.track_imports(code)

        # Use transaction context if provided
        if transaction_id:
            with self.transaction(transaction_id, policy):
                return self._execute_code(code)
        else:
            return self._execute_code(code)

    def _execute_code(self, code: str) -> Any:
        """Internal code execution.

        Args:
            code: Python code to execute

        Returns:
            Execution result if code is an expression
        """
        # Decide once: expression vs statements
        # Expression iff parseable as eval mode
        is_expr = False
        try:
            ast.parse(code, mode="eval")
            is_expr = True
        except SyntaxError:
            is_expr = False

        # Execute code exactly once based on type
        if is_expr:
            # Single expression: evaluate and capture result
            # Use dont_inherit=False to align with cooperative cancellation guidance
            compiled = compile(code, "<session>", "eval", dont_inherit=False, optimize=0)
            return eval(compiled, self._namespace)
        else:
            # Statements: execute without result capture
            # Use dont_inherit=False to align with cooperative cancellation guidance
            compiled = compile(code, "<session>", "exec", dont_inherit=False, optimize=0)
            exec(compiled, self._namespace)
            return None

    def update_function_sources(self, sources: Dict[str, str]) -> None:
        """Update function sources.

        Args:
            sources: Dictionary of function names to source code
        """
        self._function_sources.update(sources)

    def update_class_sources(self, sources: Dict[str, str]) -> None:
        """Update class sources.

        Args:
            sources: Dictionary of class names to source code
        """
        self._class_sources.update(sources)

    def add_imports(self, imports: list[str]) -> None:
        """Add imports to the tracked list.

        Args:
            imports: List of import statements
        """
        for imp in imports:
            if imp not in self._imports:
                self._imports.append(imp)

    def clear(self) -> None:
        """Clear the namespace and tracked sources.

        Preserves engine internals while clearing user-defined content.
        """
        # Save engine internals before clearing
        saved_internals: Dict[str, Any] = {}
        for key in ENGINE_INTERNALS:
            if key in self._namespace:
                saved_internals[key] = self._namespace[key]

        # Clear everything
        self._namespace.clear()
        self._function_sources.clear()
        self._class_sources.clear()
        self._imports.clear()
        self._snapshots.clear()

        # Restore initial state (will preserve internals via update)
        self._setup_namespace()

        # Restore any saved engine internals
        for key, value in saved_internals.items():
            self._namespace[key] = value

    def _should_update_smart(self, key: str, new_value: Any, old_value: Any) -> bool:
        """Determine if a value should be updated using smart merge strategy.

        Smart merge rules:
        - Don't update with None unless explicitly setting (preserves existing)
        - Don't update with empty containers if old value exists
        - Otherwise update if values differ

        Args:
            key: The namespace key being updated
            new_value: The new value being set
            old_value: The existing value in namespace

        Returns:
            True if the value should be updated, False otherwise
        """
        # Don't update with None unless explicitly setting
        if new_value is None and old_value is not None:
            return False

        # Don't update with empty containers if old value exists
        if isinstance(new_value, (list, dict, set)) and not new_value and old_value:
            return False

        # Update if values differ
        return bool(old_value != new_value)

    def get_serializable_namespace(self) -> Dict[str, Any]:
        """Get a serializable version of the namespace.

        Returns:
            Dictionary with serializable items only
        """
        import json

        serializable: Dict[str, Any] = {}

        for key, value in self._namespace.items():
            # Skip special attributes
            if key.startswith("__") and key.endswith("__"):
                continue

            # Check if value is JSON serializable
            try:
                json.dumps(value)
                serializable[key] = value
            except (TypeError, ValueError):
                # Store type information for non-serializable
                serializable[f"__{key}__type"] = str(type(value))

        return serializable

    def get_namespace_info(self) -> Dict[str, Any]:
        """Get information about the namespace.

        Returns:
            Dictionary with namespace statistics
        """
        import sys

        # Count different types of objects
        functions = 0
        classes = 0
        modules = 0
        other = 0

        for key, value in self._namespace.items():
            if key.startswith("__") and key.endswith("__"):
                continue

            if callable(value):
                if isinstance(value, type):
                    classes += 1
                else:
                    functions += 1
            elif isinstance(value, type(sys)):
                modules += 1
            else:
                other += 1

        return {
            "total_items": len(self._namespace),
            "functions": functions,
            "classes": classes,
            "modules": modules,
            "other": other,
            "tracked_functions": len(self._function_sources),
            "tracked_classes": len(self._class_sources),
            "tracked_imports": len(self._imports),
            "active_transactions": len(self._snapshots),
        }
