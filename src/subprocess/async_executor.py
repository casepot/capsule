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
import inspect
from typing import Any, Set
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
        # Don't try to get loop during init; get it when needed in execute()
        self.loop = None  # Will be set when needed in async context
        
        # Future: Coroutine tracking for cleanup
        self._pending_coroutines: Set[weakref.ref] = set()
        
        # AST cache with LRU limit to prevent unbounded growth
        self._ast_cache: OrderedDict[str, ast.AST] = OrderedDict()
        # TODO: Make cache size configurable via constructor parameter
        self._ast_cache_max_size = 100  # Limit cache size
        
        # Execution statistics
        self.stats = {
            "executions": 0,
            "errors": 0
        }
        self.mode_counts = {mode: 0 for mode in ExecutionMode}
        
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
            # Use MD5 for cache keys (non-cryptographic use) for speed.
            # If we ever need a stronger digest (e.g., cross-process cache
            # keys or security-sensitive contexts), we can switch to SHA-256
            # without changing behavior elsewhere.
            code_hash = hashlib.md5(code.encode()).hexdigest()
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
            # Try compiling with TOP_LEVEL_AWAIT flag to verify if it's actually top-level await
            # This distinguishes true top-level await from invalid contexts like 'lambda: await foo()'
            try:
                compile(code, '<exec>', 'exec', flags=self.PyCF_ALLOW_TOP_LEVEL_AWAIT)
                # If it compiles with the flag, it's genuine top-level await
                logger.debug("Detected TOP_LEVEL_AWAIT mode via PyCF_ALLOW_TOP_LEVEL_AWAIT compile")
                return ExecutionMode.TOP_LEVEL_AWAIT
            except SyntaxError:
                # Not valid even with top-level await flag - it's an error
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
        
        TODO(Phase 1): Extend detection to handle attribute calls such as
        `time.sleep()`, `requests.get()`, and `socket.socket().recv()`. This
        likely requires resolving `ast.Attribute` chains and mapping imported
        names to modules. Add tests first to capture common patterns before
        broadening detection to reduce false positives.
        
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
        self.mode_counts[mode] += 1
        
        logger.info(
            "execute_start",
            execution_id=self.execution_id,
            mode=mode.value,
            code_length=len(code),
            has_event_loop=self.loop is not None,
            stats_executions=self.stats["executions"]
        )
        
        try:
            if mode == ExecutionMode.TOP_LEVEL_AWAIT:
                # Phase 1: Use native top-level await support
                return await self._execute_top_level_await(code)
            
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
        finally:
            # Always cleanup coroutines after execution
            cleaned = self.cleanup_coroutines()
            if cleaned > 0:
                logger.debug(
                    "Cleaned coroutines after execution",
                    count=cleaned,
                    execution_id=self.execution_id
                )
    
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
        # TODO: Consider pooling ThreadedExecutor instances to reduce allocation overhead
        # This would be beneficial for high-concurrency scenarios during the transition phase
        
        # Get current running loop - we're in async method so this should work
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "AsyncExecutor.execute() must be called from within an async context. "
                "Use 'await executor.execute(code)' inside an async function."
            )
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
    
    async def _execute_top_level_await(self, code: str) -> Any:
        """
        Execute code with top-level await support.
        
        Uses PyCF_ALLOW_TOP_LEVEL_AWAIT flag for direct compilation
        when possible, falls back to AST transformation if needed.
        
        Args:
            code: Python code containing top-level await
            
        Returns:
            Execution result (for expressions) or None (for statements)
            
        Raises:
            Any exception from code execution
        """
        # Following spec lines 306-339 exactly
        # Get base compile flags
        base_flags = compile('', '', 'exec').co_flags
        
        # Add the magic flag for top-level await
        flags = base_flags | self.PyCF_ALLOW_TOP_LEVEL_AWAIT
        
        try:
            # Compile with top-level await support
            compiled = compile(code, '<async_session>', 'exec', flags=flags)
            
            # Create execution namespace
            local_ns = {}
            global_ns = self.namespace.namespace.copy()
            
            # Ensure asyncio is available
            if 'asyncio' not in global_ns:
                import asyncio as _asyncio
                global_ns['asyncio'] = _asyncio
            
            # Execute - eval returns coroutine if await present
            # This is the key difference from regular exec()
            coro_or_result = eval(compiled, global_ns, local_ns)
            
            # Handle based on type
            result = None
            if inspect.iscoroutine(coro_or_result):
                # Track coroutine for cleanup
                self._track_coroutine(coro_or_result)
                # Await the coroutine
                result = await coro_or_result
            else:
                # Not a coroutine, might be direct result or None
                result = coro_or_result
                
            # Update namespace with changes (merge, don't replace!)
            # This captures any variables assigned during execution
            if local_ns:
                changes = self.namespace.update_namespace(
                    local_ns,
                    source_context='async'
                )
                logger.debug(
                    "Namespace updated after top-level await",
                    changes_count=len(changes),
                    execution_id=self.execution_id
                )
            
            # Track expression results in history
            if result is not None:
                self.namespace.record_expression_result(result)
            
            return result
            
        except SyntaxError as e:
            # Compilation failed, try AST transformation
            logger.debug(
                "Direct compilation failed, trying AST transformation",
                error=str(e),
                execution_id=self.execution_id
            )
            return await self._execute_with_ast_transform(code)
    
    async def _execute_with_ast_transform(self, code: str) -> Any:
        """
        Transform code for top-level await execution.
        
        Wraps code in async function when direct compilation
        with PyCF_ALLOW_TOP_LEVEL_AWAIT fails.
        
        Following spec lines 372-429 using AST manipulation.
        
        Args:
            code: Python code with top-level await
            
        Returns:
            Execution result
            
        Raises:
            Any exception from code execution
        """
        # Increment AST transform count for stats
        if "ast_transforms" not in self.stats:
            self.stats["ast_transforms"] = 0
        self.stats["ast_transforms"] += 1
        
        # Parse code into AST
        tree = ast.parse(code)
        
        # Check if the code is a single expression
        is_expression = len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr)
        
        # Prepare body for async function
        if is_expression:
            # For expressions, we need to return the value
            # Convert Expr node to Return node
            expr_node = tree.body[0]
            return_node = ast.Return(value=expr_node.value)
            body = [return_node]
        else:
            # For statements, we need to capture local variables
            # Add a return statement that returns locals()
            body = tree.body + [
                ast.Return(
                    value=ast.Call(
                        func=ast.Name(id='locals', ctx=ast.Load()),
                        args=[],
                        keywords=[]
                    )
                )
            ]
        
        # Create async wrapper function at AST level
        # This directly follows spec lines 385-399
        async_wrapper = ast.AsyncFunctionDef(
            name='__async_exec__',
            args=ast.arguments(
                posonlyargs=[],
                args=[],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[]
            ),
            body=body,  # Use prepared body with return if expression
            decorator_list=[],
            returns=None,
            lineno=1,
            col_offset=0
        )
        
        # Create new module with wrapper
        new_module = ast.Module(
            body=[async_wrapper],
            type_ignores=[]
        )
        
        # Fix line numbers for error reporting
        ast.fix_missing_locations(new_module)
        
        # Compile transformed AST
        compiled = compile(new_module, '<async_transform>', 'exec')
        
        # Execute to define the async function
        local_ns = {}
        global_ns = self.namespace.namespace.copy()
        
        # Ensure asyncio is available
        if 'asyncio' not in global_ns:
            import asyncio as _asyncio
            global_ns['asyncio'] = _asyncio
        
        # Execute to define the function
        exec(compiled, global_ns, local_ns)
        
        # Get the async function (it will be in local_ns)
        async_func = local_ns.get('__async_exec__')
        if not async_func:
            # Try global namespace too
            async_func = global_ns.get('__async_exec__')
        
        if not async_func:
            raise RuntimeError("Failed to create async wrapper function")
        
        # Execute the async function
        # The function will have access to global_ns as its globals
        result = await async_func()
        
        # Handle the result based on what we're expecting
        if is_expression:
            # For expressions, result is the actual value
            pass
        else:
            # For statements, result is locals() dict
            if isinstance(result, dict):
                # Extract local variables (excluding internals)
                local_vars = result
                updates = {}
                for key, value in local_vars.items():
                    # Skip special variables
                    if key.startswith('__'):
                        continue
                    if key == 'asyncio':
                        continue
                    # Add to updates
                    updates[key] = value
                
                # Update namespace with local variables
                if updates:
                    changes = self.namespace.update_namespace(
                        updates,
                        source_context='async'
                    )
                    logger.debug(
                        "Namespace updated from AST transform locals",
                        changes_count=len(changes),
                        execution_id=self.execution_id
                    )
                
                # For statements, return None
                result = None
            else:
                # Unexpected case - log and continue
                logger.warning(
                    "Expected dict from locals() but got",
                    result_type=type(result).__name__,
                    execution_id=self.execution_id
                )
        
        # Also check for any global changes (in case of global declarations)
        updates = {}
        for key, value in global_ns.items():
            # Skip special variables and functions
            if key.startswith('__') and key not in ['__name__', '__doc__']:
                continue
            if key == '__async_exec__':
                continue
            if callable(value) and key == 'asyncio':
                continue
            
            # Check if this is new or changed
            if key not in self.namespace.namespace:
                updates[key] = value
            elif self.namespace.namespace.get(key) != value:
                updates[key] = value
        
        # Update namespace with changes
        if updates:
            changes = self.namespace.update_namespace(
                updates,
                source_context='async'
            )
            logger.debug(
                "Namespace updated from AST transform",
                changes_count=len(changes),
                execution_id=self.execution_id
            )
        
        # Track result if it's an expression
        if result is not None:
            self.namespace.record_expression_result(result)
            
        logger.debug(
            "AST transformation completed",
            result_type=type(result).__name__ if result is not None else "None",
            has_namespace_updates=len(updates) > 0,
            execution_id=self.execution_id
        )
        
        return result
    
    def _track_coroutine(self, coro) -> None:
        """
        Track a coroutine for cleanup.
        
        Uses weak reference to avoid keeping coroutine alive unnecessarily.
        
        Args:
            coro: Coroutine to track
        """
        import weakref
        # Use weak reference to avoid keeping coroutine alive
        self._pending_coroutines.add(weakref.ref(coro))
        logger.debug(
            "Tracking coroutine",
            coroutine=str(coro),
            total_tracked=len(self._pending_coroutines),
            execution_id=self.execution_id
        )
    
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
