"""AsyncExecutor skeleton implementation for transition to async architecture.

This module provides the foundation for async execution support, including
top-level await capability via the PyCF_ALLOW_TOP_LEVEL_AWAIT compile flag.

During Phase 0, this is a skeleton that delegates to ThreadedExecutor.
Future phases will implement full async execution capabilities.
"""

from __future__ import annotations

import ast
import asyncio
from collections import OrderedDict
from enum import Enum
import hashlib
from typing import Any, Dict, Set
import weakref

import structlog

from .executor import ThreadedExecutor
from .namespace import NamespaceManager
from ..protocol.transport import MessageTransport

logger = structlog.get_logger()


class ExecutionMode(Enum):
    """Execution modes for code analysis."""
    TOP_LEVEL_AWAIT = "top_level_await"
    ASYNC_DEF = "async_def"
    BLOCKING_SYNC = "blocking_sync"
    SIMPLE_SYNC = "simple_sync"
    UNKNOWN = "unknown"


class AsyncExecutor:
    """
    Skeleton async executor for transition to async architecture.
    
    This is a Phase 0 implementation that:
    - Provides the AsyncExecutor interface expected by tests
    - Analyzes code to detect execution modes
    - Delegates actual execution to ThreadedExecutor
    - Prepares for future async implementation
    
    Key Features (skeleton only):
    - PyCF_ALLOW_TOP_LEVEL_AWAIT constant defined
    - Execution mode detection via AST analysis
    - Event loop management
    - Namespace merge-only policy enforcement
    """
    
    # Critical discovery from PyCF_ALLOW_TOP_LEVEL_AWAIT research
    # This compile flag enables top-level await in Python 3.11+
    PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x1000000
    
    # Blocking I/O indicators for execution mode detection
    BLOCKING_IO_MODULES = {
        'requests', 'urllib', 'socket', 'subprocess',
        'sqlite3', 'psycopg2', 'pymongo', 'redis'
    }
    
    BLOCKING_IO_CALLS = {
        'open', 'input', 'sleep', 'wait',
        'read', 'write', 'recv', 'send'
    }
    
    def __init__(
        self,
        namespace_manager: NamespaceManager,
        transport: MessageTransport,
        execution_id: str
    ):
        """
        Initialize AsyncExecutor skeleton.
        
        Args:
            namespace_manager: Namespace manager (GIL-protected for basic operations)
            transport: Message transport for output
            execution_id: Unique execution identifier
            
        Note:
            - Thread safety: The namespace manager relies on Python's GIL
              for basic thread safety. Explicit synchronization may be needed
              for complex operations in production use.
            - In future phases, this will accept a Resonate instance
              instead of transport for durability support.
        """
        self.namespace = namespace_manager
        self.transport = transport
        self.execution_id = execution_id
        
        # Event loop management - never modify global loop
        # Always use existing loop or None if not in async context
        try:
            self.loop = asyncio.get_running_loop()
            logger.debug("Using existing event loop")
        except RuntimeError:
            # No running loop - that's ok, we'll get it when needed
            self.loop = None
            logger.debug("No event loop available yet")
        
        # Future: Coroutine tracking for cleanup
        self._pending_coroutines: Set[weakref.ref] = set()
        
        # AST cache with LRU limit to prevent unbounded growth
        self._ast_cache: OrderedDict[str, ast.AST] = OrderedDict()
        self._ast_cache_max_size = 100  # Limit cache size
        
        # Execution statistics
        self.stats = {
            "executions": 0,
            "mode_counts": {mode: 0 for mode in ExecutionMode},
            "errors": 0,
            "ast_transforms": 0
        }
        
        logger.info(
            "AsyncExecutor initialized",
            execution_id=execution_id,
            has_loop=self.loop is not None
        )
    
    def analyze_execution_mode(self, code: str) -> ExecutionMode:
        """
        Determine optimal execution mode for code.
        
        Analysis Steps:
        1. Try standard AST parsing
        2. Check for top-level await expressions
        3. Detect async function definitions
        4. Identify blocking I/O patterns
        5. Default to simple sync
        
        Args:
            code: Python code to analyze
            
        Returns:
            ExecutionMode enum value
        """
        try:
            # Try to parse code normally
            tree = ast.parse(code)
            
            # Store in cache with LRU eviction
            # Use stable SHA-256 digest instead of hash() to avoid collisions
            code_hash = hashlib.sha256(code.encode()).hexdigest()
            if code_hash in self._ast_cache:
                # Move to end (most recently used)
                self._ast_cache.move_to_end(code_hash)
            else:
                self._ast_cache[code_hash] = tree
                # Evict oldest if cache is too large
                if len(self._ast_cache) > self._ast_cache_max_size:
                    self._ast_cache.popitem(last=False)
            
            # Check for top-level await (not inside function)
            # Need to check all nodes, not just Expr nodes
            for node in tree.body:
                if self._contains_await_at_top_level(node):
                    logger.debug("Detected TOP_LEVEL_AWAIT mode")
                    return ExecutionMode.TOP_LEVEL_AWAIT
            
            # Check for async function definitions
            has_async_def = False
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    has_async_def = True
                    break
            
            if has_async_def:
                logger.debug("Detected ASYNC_DEF mode")
                return ExecutionMode.ASYNC_DEF
            
            # Check for blocking I/O patterns
            if self._contains_blocking_io(tree):
                logger.debug("Detected BLOCKING_SYNC mode")
                return ExecutionMode.BLOCKING_SYNC
            
            # Default to simple sync
            logger.debug("Detected SIMPLE_SYNC mode")
            return ExecutionMode.SIMPLE_SYNC
            
        except SyntaxError as e:
            # Code likely contains top-level await that doesn't parse
            if 'await' in str(e) or 'await' in code:
                logger.debug("Detected TOP_LEVEL_AWAIT mode from SyntaxError")
                return ExecutionMode.TOP_LEVEL_AWAIT
            # Unknown syntax error
            logger.debug("Detected UNKNOWN mode from SyntaxError", error=str(e))
            return ExecutionMode.UNKNOWN
    
    def _contains_await_at_top_level(self, node: ast.AST) -> bool:
        """
        Check if node contains await at module level.
        
        Recursively walks AST to find Await nodes that are
        not inside function definitions.
        
        Args:
            node: AST node to check
            
        Returns:
            True if contains top-level await
        """
        # Direct await node
        if isinstance(node, ast.Await):
            return True
        
        # Don't recurse into function definitions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return False
        
        # For assignments, check the value
        if isinstance(node, ast.Assign):
            if self._contains_await_at_top_level(node.value):
                return True
        
        # For expressions, check the value
        if isinstance(node, ast.Expr):
            if self._contains_await_at_top_level(node.value):
                return True
        
        # Check all child nodes recursively
        for child in ast.iter_child_nodes(node):
            # Skip function definitions
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                if self._contains_await_at_top_level(child):
                    return True
        
        return False
    
    def _contains_blocking_io(self, tree: ast.AST) -> bool:
        """
        Detect blocking I/O operations in code.
        
        Checks for:
        - Imports of blocking libraries
        - Calls to blocking functions
        - File operations without async
        
        Args:
            tree: AST tree to analyze
            
        Returns:
            True if contains blocking I/O
        """
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    if module_name in self.BLOCKING_IO_MODULES:
                        return True
            
            # Check from imports
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    if module_name in self.BLOCKING_IO_MODULES:
                        return True
            
            # Check function calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.BLOCKING_IO_CALLS:
                        # Could check if it's in async context, but for
                        # skeleton we'll just flag it as blocking
                        return True
        
        return False
    
    async def execute(self, code: str) -> Any:
        """
        Main execution entry point (skeleton implementation).
        
        Analyzes code and routes to appropriate execution method.
        Currently delegates to ThreadedExecutor for all execution.
        
        Args:
            code: Python code to execute
            
        Returns:
            Execution result
            
        Raises:
            NotImplementedError: For TOP_LEVEL_AWAIT mode (future work)
            Any exception raised during execution
        """
        self.stats["executions"] += 1
        
        # Analyze execution mode
        mode = self.analyze_execution_mode(code)
        self.stats["mode_counts"][mode] += 1
        
        logger.info(
            "Executing code",
            execution_id=self.execution_id,
            mode=mode.value,
            code_length=len(code)
        )
        
        try:
            if mode == ExecutionMode.TOP_LEVEL_AWAIT:
                # TODO(Phase 1): Implement using compile() with PyCF_ALLOW_TOP_LEVEL_AWAIT flag
                raise NotImplementedError("Async execution coming soon - Phase 1")
            
            else:
                # All other modes delegate to ThreadedExecutor for now
                return await self._execute_with_threaded_executor(code)
                
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(
                "Execution failed",
                execution_id=self.execution_id,
                mode=mode.value,
                error=str(e)
            )
            raise
    
    async def _execute_with_threaded_executor(self, code: str) -> Any:
        """
        Execute code using ThreadedExecutor delegation.
        
        This is the Phase 0 implementation that maintains
        compatibility while we transition to full async.
        
        Args:
            code: Python code to execute
            
        Returns:
            Execution result
        """
        # Create ThreadedExecutor instance
        # Note: We pass namespace.namespace to get the dict
        # Get current running loop for the executor
        try:
            current_loop = self.loop or asyncio.get_running_loop()
        except RuntimeError as e:
            raise RuntimeError(
                f"AsyncExecutor.execute() must be called from async context: {e}"
            ) from e
        executor = ThreadedExecutor(
            transport=self.transport,
            execution_id=self.execution_id,
            namespace=self.namespace.namespace,  # Pass the dict
            loop=current_loop  # Use current running loop
        )
        
        # Start output pump for the executor
        await executor.start_output_pump()
        
        try:
            # Use the async wrapper we added in Phase 0
            result = await executor.execute_code_async(code)
            
            # CRITICAL: Update namespace with merge-only policy
            # The ThreadedExecutor modifies the namespace dict directly,
            # but we need to ensure any new keys are properly tracked
            # Note: ThreadedExecutor already updates the dict in-place,
            # so we don't need to do anything extra here
            
            return result
            
        finally:
            # Always stop output pump
            await executor.stop_output_pump()
    
    def cleanup_coroutines(self) -> int:
        """
        Clean up any pending coroutines (future implementation).
        
        Returns:
            Number of coroutines cleaned
        """
        cleaned = 0
        dead_refs = []
        
        for coro_ref in self._pending_coroutines:
            coro = coro_ref()
            if coro is None:
                # Reference is dead
                dead_refs.append(coro_ref)
            else:
                try:
                    coro.close()
                    cleaned += 1
                except Exception:
                    pass  # Already closed or running
        
        # Remove dead references
        for ref in dead_refs:
            self._pending_coroutines.discard(ref)
        
        return cleaned
    
    async def close(self):
        """Explicitly close the executor and clean up resources.
        
        This should be called when the executor is no longer needed.
        Alternatively, use AsyncExecutor as a context manager.
        """
        cleaned = self.cleanup_coroutines()
        if cleaned > 0:
            logger.debug(f"Cleaned up {cleaned} pending coroutines")
    
    async def __aenter__(self):
        """Enter context manager."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and clean up."""
        await self.close()
        return False