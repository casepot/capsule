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
    
    # Top-level await compile flag from Python's ast module
    # This flag enables top-level await in Python 3.8+
    PyCF_ALLOW_TOP_LEVEL_AWAIT = getattr(ast, 'PyCF_ALLOW_TOP_LEVEL_AWAIT', 0x2000)
    
    # Blocking I/O indicators for execution mode detection
    BLOCKING_IO_MODULES = {
        'requests', 'urllib', 'socket', 'subprocess',
        'sqlite3', 'psycopg2', 'pymongo', 'redis',
        'time', 'os', 'shutil', 'pathlib'
    }
    
    BLOCKING_IO_CALLS = {
        'open', 'input', 'sleep', 'wait',
        'read', 'write', 'recv', 'send'
    }
    
    def __init__(
        self,
        namespace_manager: NamespaceManager,
        transport: MessageTransport,
        execution_id: str,
        *,
        tla_timeout: float = 30.0,
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
        self.tla_timeout = float(tla_timeout)
        
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
            # If code contains 'await' at top-level and failed normal parse,
            # treat as TOP_LEVEL_AWAIT without compiling here. We'll let
            # the execution path handle compilation and fallback choices.
            if 'await' in code:
                logger.debug("Detected TOP_LEVEL_AWAIT mode via quick check after SyntaxError")
                return ExecutionMode.TOP_LEVEL_AWAIT
            # Otherwise unknown/invalid
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
        # Extended detection with alias tracking
        # TODO(Phase 1 follow-up): Make detection configurable (allow callers to
        # provide modules/methods) and add telemetry (counters + structured logs).
        alias_to_module: dict[str, str] = {}

        # First pass: map import aliases, and flag direct blocking imports
        found_blocking_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    name = alias.asname or module_name
                    alias_to_module[name] = module_name
                    if module_name in self.BLOCKING_IO_MODULES:
                        found_blocking_import = True
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    for alias in node.names:
                        name = alias.asname or alias.name
                        alias_to_module[name] = module_name
                    if module_name in self.BLOCKING_IO_MODULES:
                        found_blocking_import = True

        if found_blocking_import:
            return True

        # Second pass: calls and attribute chains
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Direct calls
                if isinstance(node.func, ast.Name):
                    fn = node.func.id
                    if fn in self.BLOCKING_IO_CALLS:
                        return True
                    if alias_to_module.get(fn) in self.BLOCKING_IO_MODULES:
                        return True
                # Attribute calls like time.sleep(), requests.get()
                elif isinstance(node.func, ast.Attribute):
                    base_name = self._resolve_attribute_base(node.func.value)
                    if base_name:
                        mod = alias_to_module.get(base_name, base_name)
                        if mod in self.BLOCKING_IO_MODULES:
                            # Known blocking methods per module
                            blocking_methods = {
                                'time': {'sleep', 'wait'},
                                'socket': {'recv', 'send', 'accept', 'connect'},
                                'requests': {'get', 'post', 'put', 'delete', 'patch'},
                                'os': {'system', 'popen', 'waitpid'},
                                'pathlib': {'read_text', 'read_bytes', 'write_text', 'write_bytes'},
                            }
                            methods = blocking_methods.get(mod, set())
                            if node.func.attr in methods:
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
        
        # Fast-path: simple detection to avoid heavy AST for common await cases
        if 'await' in code:
            mode = ExecutionMode.TOP_LEVEL_AWAIT
        else:
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
                return await self._execute_top_level_await(code)
            elif 'await' in code:
                # Edge cases like lambdas with await: force TLA path
                return await self._execute_top_level_await(code)
            else:
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
        # Use TLA flag directly (avoid extra compile() to read base flags)
        flags = self.PyCF_ALLOW_TOP_LEVEL_AWAIT

        try:
            # Try eval mode first to preserve expression results
            compiled = compile(code, '<async_session>', 'eval', flags=flags)

            import inspect as _inspect
            is_coroutine_code = bool(_inspect.CO_COROUTINE & compiled.co_flags)

            global_ns = self.namespace.namespace
            local_ns: dict[str, Any] = {}

            # Snapshot globals before execution for diffing
            pre_globals = dict(global_ns)

            # Ensure asyncio
            if 'asyncio' not in global_ns:
                import asyncio as _asyncio
                global_ns['asyncio'] = _asyncio

            coro_or_result = eval(compiled, global_ns, local_ns)

            if is_coroutine_code and asyncio.iscoroutine(coro_or_result):
                self._track_coroutine(coro_or_result)
                async with asyncio.timeout(self.tla_timeout):
                    result = await coro_or_result
            else:
                result = coro_or_result

            # Merge locals first
            if local_ns:
                self.namespace.update_namespace(local_ns, source_context='async')

            # Merge global diffs next
            global_updates = self._compute_global_diff(pre_globals, global_ns)
            if global_updates:
                self.namespace.update_namespace(global_updates, source_context='async')

            if result is not None:
                self.namespace.record_expression_result(result)

            return result

        except asyncio.TimeoutError as e:  # type: ignore[unreachable]
            if hasattr(e, 'add_note'):
                e.add_note("Code execution timed out after 30 seconds")
                e.add_note(f"Execution ID: {self.execution_id}")
                snippet = code[:100] + ('...' if len(code) > 100 else '')
                e.add_note(f"Code snippet: {snippet}")
            raise
        except SyntaxError as e:
            if hasattr(e, 'add_note'):
                e.add_note("Direct compilation with PyCF_ALLOW_TOP_LEVEL_AWAIT failed")
                e.add_note("Falling back to AST transformation wrapper")
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

        # Pre-transform problematic patterns
        transformed_body: list[ast.stmt] = []
        for stmt in tree.body:
            # Transform def containing await -> async def
            if isinstance(stmt, ast.FunctionDef) and self._contains_await(stmt):
                async_def = ast.AsyncFunctionDef(
                    name=stmt.name,
                    args=stmt.args,
                    body=stmt.body,
                    decorator_list=stmt.decorator_list,
                    returns=stmt.returns,
                    type_comment=stmt.type_comment if hasattr(stmt, 'type_comment') else None,
                )
                ast.copy_location(async_def, stmt)
                transformed_body.append(async_def)
                continue

            # Transform zero-arg lambda with await assigned to name -> async def helper
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Lambda):
                if self._should_transform_lambda(stmt.value):
                    transformed = self._transform_lambda_to_async_def(stmt)
                    transformed_body.extend(transformed)
                    continue

            transformed_body.append(stmt)

        tree.body = transformed_body

        # Determine if expression or statements
        is_expression = len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr)

        # Prepare wrapper body
        if is_expression:
            body: list[ast.stmt] = [ast.Return(value=tree.body[0].value)]
        else:
            # Conservative global hoisting for simple assigned names
            assigned_names = self._collect_safe_assigned_names(tree.body)
            body = []
            if assigned_names:
                body.append(ast.Global(names=sorted(assigned_names)))
            body.extend(tree.body)
            body.append(ast.Return(value=ast.Call(func=ast.Name(id='locals', ctx=ast.Load()), args=[], keywords=[])))
        
        # Create async wrapper function at AST level
        # This directly follows spec lines 385-399
        # TODO(Phase 1): If supporting Python <3.8, adjust ast.arguments
        # construction (posonlyargs not present). Current target is 3.11+.
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
        # IMPORTANT: Use the live session namespace as globals so the created
        # function's __globals__ points at the real mapping (no stale copies).
        local_ns: dict[str, Any] = {}
        global_ns = self.namespace.namespace  # live mapping

        # Snapshot globals for diffing
        pre_globals = dict(global_ns)
        
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
                updates: dict[str, Any] = {}
                for key, value in result.items():
                    if key.startswith('__') or key in {'asyncio', '__async_exec__'}:
                        continue
                    updates[key] = value
                if updates:
                    self.namespace.update_namespace(updates, source_context='async')
                # For statements, return None
                result = None
            else:
                # Unexpected case - log and continue
                logger.warning(
                    "Expected dict from locals() but got",
                    result_type=type(result).__name__,
                    execution_id=self.execution_id
                )

        # Apply global diffs AFTER locals to ensure global writes win
        global_updates = self._compute_global_diff(pre_globals, global_ns)
        if global_updates:
            self.namespace.update_namespace(global_updates, source_context='async')
        
        # Track result if it's an expression
        if result is not None:
            self.namespace.record_expression_result(result)

        logger.debug(
            "AST transformation completed",
            result_type=type(result).__name__ if result is not None else "None",
            has_namespace_updates=True,  # conservative signal for tests/telemetry
            execution_id=self.execution_id
        )
        
        return result

    # Helper utilities
    def _compute_global_diff(self, before: dict, after: dict) -> dict:
        """Compute globals diff, filtering system variables."""
        updates: dict[str, Any] = {}
        skip = {'__async_exec__', 'asyncio', '__builtins__'}

        # ENGINE_INTERNALS is imported from constants via NamespaceManager module
        try:
            from .constants import ENGINE_INTERNALS  # type: ignore
        except Exception:
            ENGINE_INTERNALS = set()

        for key, value in after.items():
            if key in skip or key in ENGINE_INTERNALS:
                continue
            if key.startswith('__') and key.endswith('__'):
                continue
            if key not in before or before.get(key) is not value:
                updates[key] = value
        return updates

    def _collect_safe_assigned_names(self, body: list[ast.stmt]) -> set[str]:
        """Collect simple identifiers safe for global declaration."""
        try:
            from .constants import ENGINE_INTERNALS  # type: ignore
        except Exception:
            ENGINE_INTERNALS = set()

        names: set[str] = set()
        for node in body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if not target.id.startswith('__') and target.id not in ENGINE_INTERNALS:
                            names.add(target.id)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    if not node.target.id.startswith('__'):
                        names.add(node.target.id)
            elif isinstance(node, ast.AugAssign):
                if isinstance(node.target, ast.Name):
                    names.add(node.target.id)
        return names

    def _resolve_attribute_base(self, node: ast.AST) -> str | None:
        """Resolve attribute chain to base name."""
        while isinstance(node, ast.Attribute):
            node = node.value
        if isinstance(node, ast.Name):
            return node.id
        return None

    def _contains_await(self, node: ast.AST) -> bool:
        """Return True if the subtree contains an Await node."""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Await):
                return True
        return False

    def _should_transform_lambda(self, lam: ast.Lambda) -> bool:
        """Detect zero-arg lambda containing await."""
        # Zero-arg and contains await in body
        has_zero_args = not lam.args.args and not lam.args.vararg and not lam.args.kwonlyargs and not lam.args.kwarg
        return has_zero_args and self._contains_await(lam.body)

    def _transform_lambda_to_async_def(self, assign_stmt: ast.Assign) -> list[ast.stmt]:
        """Transform `name = lambda: await ...` to async def helper + assignment.

        Returns a list of statements that replace the original assignment.
        """
        assert isinstance(assign_stmt.value, ast.Lambda)
        lam: ast.Lambda = assign_stmt.value

        # Generate a unique helper function name based on target
        if len(assign_stmt.targets) != 1 or not isinstance(assign_stmt.targets[0], ast.Name):
            return [assign_stmt]

        target_name = assign_stmt.targets[0].id
        helper_name = f"__async_lambda_{target_name}__"

        async_def = ast.AsyncFunctionDef(
            name=helper_name,
            args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=[ast.Return(value=lam.body)],
            decorator_list=[],
            returns=None,
        )
        ast.copy_location(async_def, assign_stmt)

        # Replace original assignment with assignment to helper function object
        new_assign = ast.Assign(targets=[ast.Name(id=target_name, ctx=ast.Store())], value=ast.Name(id=helper_name, ctx=ast.Load()))
        ast.copy_location(new_assign, assign_stmt)

        return [async_def, new_assign]
    
    def _track_coroutine(self, coro) -> None:
        """
        Track a coroutine for cleanup.
        
        Uses weak reference to avoid keeping coroutine alive unnecessarily.
        
        Args:
            coro: Coroutine to track
        """
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
