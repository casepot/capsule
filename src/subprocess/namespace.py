from __future__ import annotations

import ast
import copy
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

import structlog

from ..protocol.messages import TransactionPolicy

logger = structlog.get_logger()


class NamespaceManager:
    """Manages Python namespace with transaction support."""
    
    def __init__(self) -> None:
        self._namespace: Dict[str, Any] = {}
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._function_sources: Dict[str, str] = {}
        self._class_sources: Dict[str, str] = {}
        self._imports: list[str] = []
        
        # Initialize with builtins
        self._setup_namespace()
    
    def _setup_namespace(self) -> None:
        """Setup the initial namespace."""
        import builtins
        
        self._namespace = {
            "__name__": "__main__",
            "__doc__": None,
            "__package__": None,
            "__loader__": None,
            "__spec__": None,
            "__annotations__": {},
            "__builtins__": builtins,
        }
    
    @property
    def namespace(self) -> Dict[str, Any]:
        """Get the current namespace."""
        return self._namespace
    
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
            snapshot = {}
            
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
            compiled = compile(code, "<session>", "eval", dont_inherit=True, optimize=0)
            return eval(compiled, self._namespace)
        else:
            # Statements: execute without result capture
            compiled = compile(code, "<session>", "exec", dont_inherit=True, optimize=0)
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
        """Clear the namespace and tracked sources."""
        # Clear everything
        self._namespace.clear()
        self._function_sources.clear()
        self._class_sources.clear()
        self._imports.clear()
        self._snapshots.clear()
        
        # Restore initial state
        self._setup_namespace()
    
    def get_serializable_namespace(self) -> Dict[str, Any]:
        """Get a serializable version of the namespace.
        
        Returns:
            Dictionary with serializable items only
        """
        import json
        
        serializable = {}
        
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