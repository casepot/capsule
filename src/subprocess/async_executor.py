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
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, Set
import weakref
import linecache
import re
import os as _os

import structlog

from .executor import ThreadedExecutor
from .namespace import NamespaceManager
from ..protocol.transport import MessageTransport
from types import TracebackType

logger = structlog.get_logger()


class ExecutionMode(Enum):
    """Execution modes for code analysis."""

    TOP_LEVEL_AWAIT = "top_level_await"
    ASYNC_DEF = "async_def"
    BLOCKING_SYNC = "blocking_sync"
    SIMPLE_SYNC = "simple_sync"
    UNKNOWN = "unknown"


@dataclass
class _DetectionPolicy:
    """Internal detection policy with safe defaults and overrides."""

    blocking_modules: set[str] = field(
        default_factory=lambda: {
            "requests",
            "urllib",
            "socket",
            "subprocess",
            "sqlite3",
            "psycopg2",
            "pymongo",
            "redis",
            "time",
            "os",
            "shutil",
            "pathlib",
        }
    )
    # Methods per base module (base = leftmost name, e.g., 'urllib' for 'urllib.request')
    blocking_methods_by_module: dict[str, set[str]] = field(
        default_factory=lambda: {
            "time": {"sleep", "wait"},
            "socket": {"recv", "send", "accept", "connect"},
            "requests": {"get", "post", "put", "delete", "patch", "head", "options"},
            "urllib": {"urlopen"},
            "os": {"system"},
            "subprocess": {"run", "Popen", "call", "check_call", "check_output"},
            "pathlib": {"read_text", "read_bytes", "write_text", "write_bytes"},
        }
    )
    # Name calls to always treat as blocking (e.g., builtins)
    blocking_name_calls: set[str] = field(default_factory=lambda: {"open", "input"})


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
    PyCF_ALLOW_TOP_LEVEL_AWAIT = getattr(ast, "PyCF_ALLOW_TOP_LEVEL_AWAIT", 0x2000)

    # Blocking I/O indicators for execution mode detection
    # Deprecated: kept for backward-compatibility; superseded by _DetectionPolicy
    BLOCKING_IO_MODULES = _DetectionPolicy().blocking_modules
    BLOCKING_IO_CALLS = _DetectionPolicy().blocking_name_calls | {
        "sleep",
        "wait",
        "read",
        "write",
        "recv",
        "send",
    }

    def __init__(
        self,
        namespace_manager: NamespaceManager,
        transport: MessageTransport | None,
        execution_id: str,
        *,
        tla_timeout: float = 30.0,
        ast_cache_max_size: int | None = 100,
        blocking_modules: set[str] | None = None,
        blocking_methods_by_module: dict[str, set[str]] | None = None,
        warn_on_blocking: bool = True,
        enable_def_await_rewrite: bool | None = None,
        enable_async_lambda_helper: bool | None = None,
        fallback_linecache_max_size: int | None = None,
    ):
        """
        Initialize AsyncExecutor skeleton.

        Args:
            namespace_manager: Namespace manager (GIL-protected for basic operations).
            transport: Message transport for output.
            execution_id: Unique execution identifier.
            tla_timeout: Timeout in seconds applied to awaited top-level coroutines.
            ast_cache_max_size: Optional AST LRU cache size used by analysis; None disables.
            blocking_modules: Override for blocking I/O detection policy.
            blocking_methods_by_module: Override per-module blocking method names.
            warn_on_blocking: Emit logs on blocking patterns when True.
            enable_def_await_rewrite: When True, the AST fallback pre-transform rewrites
                top-level "def" whose body contains an await into "async def". When False,
                this rewrite is disabled. When None (default), environment variable
                ASYNC_EXECUTOR_ENABLE_DEF_AWAIT_REWRITE ("1"/"true"/"yes") may enable it.
            enable_async_lambda_helper: When True, the AST fallback pre-transform rewrites
                zero-arg lambda assignments of the form "name = lambda: await ..." into a
                helper async def plus assignment to preserve semantics. When False, disabled.
                When None (default), environment variable
                ASYNC_EXECUTOR_ENABLE_ASYNC_LAMBDA_HELPER ("1"/"true"/"yes") may enable it.
            fallback_linecache_max_size: Bounded LRU capacity (int >= 0) for sources
                registered in `linecache` for traceback mapping during AST fallback. If None,
                capacity is resolved via `ASYNC_EXECUTOR_FALLBACK_LINECACHE_MAX` or defaults to 128.
                A value of 0 retains no entries (evicts immediately). Entries are always cleaned
                up on `close()`.

        Notes:
            - Thread safety: The namespace manager relies on Python's GIL for basic safety.
            - AST fallback transforms run only on the fallback path (after TLA compile fails).
            - Both transforms are disabled by default to preserve user code semantics.
        """
        self.namespace = namespace_manager
        self.transport = transport
        self.execution_id = execution_id
        self.tla_timeout = float(tla_timeout)

        # Event loop management - never modify global loop
        # Don't try to get loop during init; get it when needed in execute()
        self.loop = None  # Will be set when needed in async context

        # Future: Coroutine tracking for cleanup
        self._pending_coroutines: Set[weakref.ReferenceType[Any]] = set()

        # AST cache with LRU limit to prevent unbounded growth
        self._ast_cache: OrderedDict[str, ast.AST] = OrderedDict()
        # Cache size is configurable; None disables caching entirely
        # Allow env override if arg not explicitly provided
        if ast_cache_max_size is None:
            self._ast_cache_max_size = None
        else:
            try:
                env_val = _os.getenv("ASYNC_EXECUTOR_AST_CACHE_SIZE")
                self._ast_cache_max_size = (
                    int(env_val) if env_val and ast_cache_max_size == 100 else int(ast_cache_max_size)
                )
            except Exception:
                # ast_cache_max_size is not None in this branch; coerce to int directly
                self._ast_cache_max_size = int(ast_cache_max_size)

        # Execution statistics
        self.stats = {
            "executions": 0,
            "errors": 0,
            # Telemetry counters for detection
            "detected_blocking_import": 0,
            "detected_blocking_call": 0,
            "missed_attribute_chain": 0,
        }
        self.mode_counts = {mode: 0 for mode in ExecutionMode}

        # Fallback AST transform policy flags (default OFF)
        # Allow env override only if args left at defaults (mirror cache style)
        # Resolve flags: explicit constructor args win; otherwise allow env override; default False

        if enable_def_await_rewrite is None:
            env_def = _os.getenv("ASYNC_EXECUTOR_ENABLE_DEF_AWAIT_REWRITE")
            self._enable_def_await_rewrite = bool(env_def and env_def.lower() in {"1", "true", "yes"})
        else:
            self._enable_def_await_rewrite = bool(enable_def_await_rewrite)

        if enable_async_lambda_helper is None:
            env_lambda = _os.getenv("ASYNC_EXECUTOR_ENABLE_ASYNC_LAMBDA_HELPER")
            self._enable_async_lambda_helper = bool(env_lambda and env_lambda.lower() in {"1", "true", "yes"})
        else:
            self._enable_async_lambda_helper = bool(enable_async_lambda_helper)

        # Track per-execution fallback filenames for linecache cleanup (LRU)
        self._fallback_linecache_keys: OrderedDict[str, None] = OrderedDict()
        self._fallback_seq: int = 0
        # Resolve fallback linecache capacity: None disables cleanup; default from env or 128
        if fallback_linecache_max_size is None:
            env_cap = _os.getenv("ASYNC_EXECUTOR_FALLBACK_LINECACHE_MAX")
            if env_cap is not None:
                try:
                    self._fallback_linecache_max_size = int(env_cap)
                except Exception:
                    self._fallback_linecache_max_size = 128
            else:
                self._fallback_linecache_max_size = 128
        else:
            self._fallback_linecache_max_size = fallback_linecache_max_size

        # Telemetry counters for gated transforms
        self.stats["ast_transforms"] = self.stats.get("ast_transforms", 0)
        self.stats["ast_transform_def_rewrites"] = 0
        self.stats["ast_transform_lambda_helpers"] = 0

        # Detection policy setup
        policy = _DetectionPolicy()
        if blocking_modules is not None:
            policy.blocking_modules = set(blocking_modules)
        if blocking_methods_by_module is not None:
            # Merge with defaults; user set wins for overlaps
            merged: dict[str, set[str]] = {}
            for k, v in policy.blocking_methods_by_module.items():
                merged[k] = set(v)
            for k, v in blocking_methods_by_module.items():
                merged[k] = set(v)
            policy.blocking_methods_by_module = merged
        self._policy = policy
        self._warn_on_blocking = bool(warn_on_blocking)

        logger.info(
            "AsyncExecutor initialized", execution_id=execution_id, has_loop=self.loop is not None
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

            # Optional AST cache with LRU eviction
            if self._ast_cache_max_size is not None:
                # Use MD5 for cache keys (non-cryptographic use) for speed.
                code_hash = hashlib.md5(code.encode()).hexdigest()
                if code_hash in self._ast_cache:
                    # Move to end (most recently used)
                    self._ast_cache.move_to_end(code_hash)
                else:
                    self._ast_cache[code_hash] = tree
                    # Evict oldest if cache is too large
                    if len(self._ast_cache) > int(self._ast_cache_max_size):
                        self._ast_cache.popitem(last=False)

            # Check for top-level await/async constructs (not inside function)
            # Need to check all nodes, not just Expr nodes
            for node in tree.body:
                if self._contains_await_at_top_level(node):
                    logger.debug("Detected TOP_LEVEL_AWAIT mode")
                    return ExecutionMode.TOP_LEVEL_AWAIT

            # Check for async function definitions
            has_async_def = False
            for any_node in ast.walk(tree):
                if isinstance(any_node, ast.AsyncFunctionDef):
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
            if ("await" in code) or ("async for" in code) or ("async with" in code):
                logger.debug("Detected TOP_LEVEL_AWAIT mode via quick check after SyntaxError")
                return ExecutionMode.TOP_LEVEL_AWAIT
            # Otherwise unknown/invalid
            logger.debug("Detected UNKNOWN mode from SyntaxError", error=str(e))
            return ExecutionMode.UNKNOWN

    def _contains_await_at_top_level(self, node: ast.AST) -> bool:
        """
        Check if node contains await/async constructs at module level.

        Recursively walks AST to find Await, AsyncFor, or AsyncWith nodes that are
        not inside function definitions.

        Args:
            node: AST node to check

        Returns:
            True if contains top-level await
        """
        # Direct await/async node
        if isinstance(node, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
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
        # Extended detection with alias tracking and configurable policy
        alias_to_module: dict[str, str] = {}

        # First pass: map import aliases, and flag direct blocking imports
        found_blocking_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split(".")[0]
                    name = alias.asname or module_name
                    alias_to_module[name] = module_name
                    if module_name in self._policy.blocking_modules:
                        found_blocking_import = True
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split(".")[0]
                    for alias in node.names:
                        name = alias.asname or alias.name
                        alias_to_module[name] = module_name
                    if module_name in self._policy.blocking_modules:
                        found_blocking_import = True

        found_any = False
        if found_blocking_import:
            self.stats["detected_blocking_import"] += 1
            found_any = True
            if self._warn_on_blocking:
                logger.warning("Detected blocking import", execution_id=self.execution_id)

        # Second pass: calls and attribute chains
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Direct calls
                if isinstance(node.func, ast.Name):
                    fn = node.func.id
                    # Direct name calls like open(), input(), or aliased import funcs
                    if fn in self._policy.blocking_name_calls:
                        self.stats["detected_blocking_call"] += 1
                        if self._warn_on_blocking:
                            logger.warning(
                                "Detected blocking name call",
                                function=fn,
                                execution_id=self.execution_id,
                            )
                        return True
                    resolved_mod = alias_to_module.get(fn)
                    if resolved_mod and resolved_mod in self._policy.blocking_modules:
                        # If a direct name maps to a blocking module, consider it blocking
                        self.stats["detected_blocking_call"] += 1
                        logger.info(
                            "Detected blocking aliased call",
                            alias=fn,
                            module=resolved_mod,
                            execution_id=self.execution_id,
                        )
                        return True
                # Attribute calls like time.sleep(), requests.get()
                elif isinstance(node.func, ast.Attribute):
                    base_name = self._resolve_attribute_base(node.func.value)
                    if base_name:
                        mod = alias_to_module.get(base_name, base_name)
                        if mod in self._policy.blocking_modules:
                            methods = self._policy.blocking_methods_by_module.get(mod, set())
                            if node.func.attr in methods:
                                self.stats["detected_blocking_call"] += 1
                                logger.info(
                                    "Detected blocking attribute call",
                                    module=mod,
                                    method=node.func.attr,
                                    execution_id=self.execution_id,
                                )
                                found_any = True
                    else:
                        # Could not resolve base of attribute chain (e.g., complex expr)
                        self.stats["missed_attribute_chain"] += 1
        return found_any

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
        if "await" in code:
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
            stats_executions=self.stats["executions"],
        )

        try:
            if mode == ExecutionMode.TOP_LEVEL_AWAIT:
                return await self._execute_top_level_await(code)
            elif mode == ExecutionMode.SIMPLE_SYNC:
                return await self._execute_simple_sync(code)
            elif mode == ExecutionMode.ASYNC_DEF:
                return await self._execute_async_definitions(code)
            elif mode == ExecutionMode.BLOCKING_SYNC:
                return await self._execute_with_threaded_executor(code)
            else:
                # UNKNOWN: prefer native simple path to surface SyntaxError naturally
                return await self._execute_simple_sync(code)

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(
                "Execution failed", execution_id=self.execution_id, mode=mode.value, error=str(e)
            )
            raise
        finally:
            # Always cleanup coroutines after execution
            cleaned = self.cleanup_coroutines()
            if cleaned > 0:
                logger.debug(
                    "Cleaned coroutines after execution",
                    count=cleaned,
                    execution_id=self.execution_id,
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
        if self.transport is None:
            raise RuntimeError(
                "Cannot delegate to ThreadedExecutor without a MessageTransport"
            )
        executor = ThreadedExecutor(
            transport=self.transport,
            execution_id=self.execution_id,
            namespace=self.namespace.namespace,  # Pass the dict
            loop=current_loop,  # Use current running loop
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

    async def _execute_simple_sync(self, code: str) -> Any:
        """Execute simple synchronous code natively.

        Detect expression vs statements using ast.parse(..., mode='eval').
        Execute against the live namespace mapping with merge-only semantics:
        - Merge locals first
        - Then merge global diffs computed against a pre-execution snapshot

        Returns the expression value for eval; None for exec.
        """
        logger.debug(
            "execute_simple_sync_start", execution_id=self.execution_id, code_length=len(code)
        )

        global_ns = self.namespace.namespace
        pre_globals = dict(global_ns)

        # Decide expression vs statements
        is_expr = False
        try:
            ast.parse(code, mode="eval")
            is_expr = True
        except SyntaxError:
            is_expr = False

        if is_expr:
            compiled = compile(code, "<session>", "eval", dont_inherit=False, optimize=0)
            local_ns: dict[str, Any] = {}
            value = eval(compiled, global_ns, local_ns)

            if local_ns:
                self.namespace.update_namespace(local_ns, source_context="async")

            global_updates = self._compute_global_diff(pre_globals, global_ns)
            if global_updates:
                self.namespace.update_namespace(global_updates, source_context="async")

            self.namespace.record_expression_result(value)

            logger.debug(
                "execute_simple_sync_done", execution_id=self.execution_id, result_type=type(value).__name__
            )
            return value
        else:
            compiled = compile(code, "<session>", "exec", dont_inherit=False, optimize=0)
            local_ns: dict[str, Any] = {}
            exec(compiled, global_ns, local_ns)

            if local_ns:
                self.namespace.update_namespace(local_ns, source_context="async")

            global_updates = self._compute_global_diff(pre_globals, global_ns)
            if global_updates:
                self.namespace.update_namespace(global_updates, source_context="async")

            logger.debug("execute_simple_sync_done", execution_id=self.execution_id, result_type="None")
            return None

    async def _execute_async_definitions(self, code: str) -> Any:
        """Execute blocks that define async functions natively.

        Always compile with mode='exec' and merge namespace updates
        using the same locals-first, then global-diff strategy.
        Returns None.
        """
        logger.debug(
            "execute_async_def_start", execution_id=self.execution_id, code_length=len(code)
        )

        global_ns = self.namespace.namespace
        pre_globals = dict(global_ns)

        compiled = compile(code, "<session>", "exec", dont_inherit=False, optimize=0)
        local_ns: dict[str, Any] = {}
        exec(compiled, global_ns, local_ns)

        if local_ns:
            self.namespace.update_namespace(local_ns, source_context="async")

        global_updates = self._compute_global_diff(pre_globals, global_ns)
        if global_updates:
            self.namespace.update_namespace(global_updates, source_context="async")

        logger.debug("execute_async_def_done", execution_id=self.execution_id)
        return None

    async def _execute_top_level_await(self, code: str) -> Any:
        """
        Execute code with top-level await support.

        Uses PyCF_ALLOW_TOP_LEVEL_AWAIT flag for direct compilation
        when possible, falls back to AST transformation only when
        both eval+flags and exec+flags compilation paths fail with
        SyntaxError.

        Args:
            code: Python code containing top-level await

        Returns:
            Execution result (for expressions) or None (for statements)

        Raises:
            Any exception from code execution
        """
        # Use TLA flag directly
        flags = self.PyCF_ALLOW_TOP_LEVEL_AWAIT

        # Bind to the live namespace mapping and prepare locals dict
        global_ns = self.namespace.namespace
        local_ns: dict[str, Any] = {}

        # Ensure asyncio is available in globals before snapshotting
        if "asyncio" not in global_ns:
            import asyncio as _asyncio

            global_ns["asyncio"] = _asyncio

        # Snapshot globals after ensuring asyncio is present (avoid spurious diffs)
        pre_globals = dict(global_ns)

        import inspect as _inspect

        try:
            # Eval-first to preserve expression results when possible
            compiled_eval = compile(code, "<async_session>", "eval", flags=flags)
            is_coro_eval = bool(_inspect.CO_COROUTINE & compiled_eval.co_flags)

            value = eval(compiled_eval, global_ns, local_ns)

            if is_coro_eval and asyncio.iscoroutine(value):
                self._track_coroutine(value)
                async with asyncio.timeout(self.tla_timeout):
                    result = await value
            else:
                result = value

            # locals-first merge
            if local_ns:
                self.namespace.update_namespace(local_ns, source_context="async")

            # then global diffs
            global_updates = self._compute_global_diff(pre_globals, global_ns)
            if global_updates:
                self.namespace.update_namespace(global_updates, source_context="async")

            if result is not None:
                self.namespace.record_expression_result(result)

            return result

        except asyncio.TimeoutError as e:
            self._annotate_timeout(e, code)
            raise
        except SyntaxError:
            # Attempt exec+flags path for statements and mixed content
            try:
                compiled_exec = compile(code, "<async_session>", "exec", flags=flags)
                is_coro_exec = bool(_inspect.CO_COROUTINE & compiled_exec.co_flags)

                # Use a fresh locals mapping for this path; assignments will populate it
                exec_locals: dict[str, Any] = {}

                # Fresh snapshot for accurate global diffs on this branch
                pre_globals_exec = dict(global_ns)

                value = eval(compiled_exec, global_ns, exec_locals)

                if is_coro_exec and asyncio.iscoroutine(value):
                    self._track_coroutine(value)
                    async with asyncio.timeout(self.tla_timeout):
                        result = await value
                else:
                    result = value

                # Merge locals first (exec_locals contains assigned names)
                if exec_locals:
                    self.namespace.update_namespace(exec_locals, source_context="async")

                # Then merge any global diffs
                global_updates = self._compute_global_diff(pre_globals_exec, global_ns)
                if global_updates:
                    self.namespace.update_namespace(global_updates, source_context="async")

                # Exec path typically returns None; record only if non-None
                if result is not None:
                    self.namespace.record_expression_result(result)

                return result

            except asyncio.TimeoutError as e:
                self._annotate_timeout(e, code)
                raise
            except SyntaxError as exec_syntax_err:
                # Both compilation paths failed; annotate and fallback to AST transform
                if hasattr(exec_syntax_err, "add_note"):
                    exec_syntax_err.add_note(
                        "Direct compilation with PyCF_ALLOW_TOP_LEVEL_AWAIT failed"
                    )
                    exec_syntax_err.add_note("Falling back to AST transformation wrapper")
                    snippet = code[:160] + ("..." if len(code) > 160 else "")
                    exec_syntax_err.add_note(
                        f"Execution ID: {self.execution_id}; Code snippet: {snippet}"
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
        # Increment AST transform count for stats and log entry
        self.stats["ast_transforms"] = self.stats.get("ast_transforms", 0) + 1
        logger.info(
            "ast_fallback_wrapper_start",
            execution_id=self.execution_id,
            def_rewrite_enabled=self._enable_def_await_rewrite,
            lambda_helper_enabled=self._enable_async_lambda_helper,
        )

        # Parse code into AST with per-execution virtual filename for traceback mapping
        FALLBACK_FILENAME = self._make_fallback_filename(code)
        tree = ast.parse(code, filename=FALLBACK_FILENAME, type_comments=True)

        # Apply gated transforms and rebuild body
        tree.body = self._apply_gated_transforms(tree)
        body, is_expression = self._build_wrapper_body(tree)

        # Create async wrapper function and module
        async_wrapper = ast.AsyncFunctionDef(
            name="__async_exec__",
            args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=body,
            decorator_list=[],
            returns=None,
            lineno=1,
            col_offset=0,
        )
        new_module = ast.Module(body=[async_wrapper], type_ignores=[])

        # Compile and register source for traceback mapping
        compiled = self._compile_and_register(code, new_module, FALLBACK_FILENAME)

        # Execute to define the async function
        # IMPORTANT: Use the live session namespace as globals so the created
        # function's __globals__ points at the real mapping (no stale copies).
        local_ns: dict[str, Any] = {}
        global_ns = self.namespace.namespace  # live mapping

        # Snapshot globals for diffing
        pre_globals = dict(global_ns)

        # Ensure asyncio is available
        if "asyncio" not in global_ns:
            import asyncio as _asyncio

            global_ns["asyncio"] = _asyncio

        # Execute to define the function
        exec(compiled, global_ns, local_ns)

        # Get the async function (it will be in local_ns)
        async_func = local_ns.get("__async_exec__")
        if not async_func:
            # Try global namespace too
            async_func = global_ns.get("__async_exec__")

        if not async_func:
            raise RuntimeError("Failed to create async wrapper function")

        # Execute the async function with timeout
        # The function will have access to global_ns as its globals
        # Execute wrapper and merge results
        try:
            async with asyncio.timeout(self.tla_timeout):
                result = await self._run_wrapper_and_merge(async_func, global_ns, pre_globals, is_expression, code)
        except asyncio.TimeoutError as e:
            self._annotate_timeout(e, code)
            raise

        logger.debug(
            "AST transformation completed",
            result_type=type(result).__name__ if result is not None else "None",
            has_namespace_updates=True,  # conservative signal for tests/telemetry
            execution_id=self.execution_id,
            def_rewrites=self.stats.get("ast_transform_def_rewrites", 0),
            lambda_helpers=self.stats.get("ast_transform_lambda_helpers", 0),
        )

        return result

    # === AST fallback helper methods ===
    def _apply_gated_transforms(self, tree: ast.Module) -> list[ast.stmt]:
        """Apply optional, flag-gated transforms to the module body preserving order and locations."""
        transformed_body: list[ast.stmt] = []
        for stmt in tree.body:
            if self._enable_def_await_rewrite and isinstance(stmt, ast.FunctionDef) and self._contains_await(stmt):
                async_def = ast.AsyncFunctionDef(
                    name=stmt.name,
                    args=stmt.args,
                    body=stmt.body,
                    decorator_list=stmt.decorator_list,
                    returns=stmt.returns,
                    type_comment=stmt.type_comment if hasattr(stmt, "type_comment") else None,
                )
                ast.copy_location(async_def, stmt)
                transformed_body.append(async_def)
                self.stats["ast_transform_def_rewrites"] += 1
                continue

            if (
                self._enable_async_lambda_helper
                and isinstance(stmt, ast.Assign)
                and isinstance(stmt.value, ast.Lambda)
                and self._should_transform_lambda(stmt.value)
            ):
                transformed = self._transform_lambda_to_async_def(stmt)
                if len(transformed) != 1 or transformed[0] is not stmt:
                    self.stats["ast_transform_lambda_helpers"] += 1
                transformed_body.extend(transformed)
                continue

            transformed_body.append(stmt)
        return transformed_body

    def _build_wrapper_body(self, tree: ast.Module) -> tuple[list[ast.stmt], bool]:
        """Build wrapper body with PEP 657-aligned locations; return (body, is_expression)."""
        is_expression = len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr)
        if is_expression:
            from typing import cast

            expr_node = cast(ast.Expr, tree.body[0])
            ret = ast.Return(value=expr_node.value)
            origin = expr_node.value if hasattr(expr_node, "value") else expr_node
            ast.copy_location(ret, origin)
            if hasattr(origin, "end_lineno"):
                ret.end_lineno = origin.end_lineno  # type: ignore[attr-defined]
                ret.end_col_offset = getattr(origin, "end_col_offset", 0)  # type: ignore[attr-defined]
            return [ret], True
        else:
            body = list(tree.body)
            ret_stmt = ast.Return(
                value=ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[])
            )
            origin_stmt = tree.body[-1] if tree.body else None
            if origin_stmt is not None:
                ast.copy_location(ret_stmt, origin_stmt)
                if hasattr(origin_stmt, "end_lineno"):
                    ret_stmt.end_lineno = origin_stmt.end_lineno  # type: ignore[attr-defined]
                    ret_stmt.end_col_offset = getattr(origin_stmt, "end_col_offset", 0)  # type: ignore[attr-defined]
            body.append(ret_stmt)
            return body, False

    def _compile_and_register(self, code: str, module: ast.Module, filename: str):
        """Fix locations, compile with filename, and register source in linecache (LRU-managed)."""
        ast.fix_missing_locations(module)
        compiled = compile(module, filename, "exec")
        self._register_fallback_source(filename, code)
        return compiled

    async def _run_wrapper_and_merge(
        self,
        async_func: Any,
        global_ns: dict[str, Any],
        pre_globals: dict[str, Any],
        is_expression: bool,
        code: str,
    ) -> Any:
        """Execute the wrapper, merge namespace updates, and return final result.

        Semantics:
        - Expression case (is_expression=True):
          Return the value and record it in result history via NamespaceManager.
        - Statements case (is_expression=False, expected normal path):
          The wrapper returns a `dict` from `locals()`. We merge filtered keys into the
          live namespace (locals-first), then apply global diffs, and return None.
        - Statements case (unexpected path):
          If the wrapper returns a non-dict, we warn and do NOT merge any locals. We still
          apply global diffs, and we currently return the original non-dict value (and it is
          recorded in result history). This choice preserves diagnostic visibility without
          mutating namespace in an ambiguous state.

        Deliberation note (future policy option): we could normalize the unexpected return
        type by coercing the final result to None for statements, to strictly preserve
        "statements return None" semantics. That would hide the anomalous value but align
        results across all statement paths. If we adopt that policy, update the tests and
        document the trade-off in the spec.
        """
        result = await async_func()

        if not is_expression:
            if isinstance(result, dict):
                updates: dict[str, Any] = {}
                for key, value in result.items():
                    if key.startswith("__") or key in {"asyncio", "__async_exec__"}:
                        continue
                    updates[key] = value
                if updates:
                    self.namespace.update_namespace(updates, source_context="async")
                result = None
            else:
                logger.warning(
                    "Expected dict from locals() but got",
                    result_type=type(result).__name__,
                    execution_id=self.execution_id,
                )

        global_updates = self._compute_global_diff(pre_globals, global_ns)
        if global_updates:
            self.namespace.update_namespace(global_updates, source_context="async")

        if result is not None:
            self.namespace.record_expression_result(result)
        return result

    # Helper utilities
    def _compute_global_diff(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        """Compute globals diff, filtering system variables."""
        updates: dict[str, Any] = {}
        skip = {"__async_exec__", "asyncio", "__builtins__"}

        # ENGINE_INTERNALS is imported from constants via NamespaceManager module
        try:
            from .constants import ENGINE_INTERNALS as _engine_internals
        except Exception as _e:
            logger.debug(
                "ENGINE_INTERNALS import failed; proceeding with empty set",
                error=str(_e),
                execution_id=self.execution_id,
            )
            _engine_internals = set()

        for key, value in after.items():
            if key in skip or key in _engine_internals:
                continue
            if key.startswith("__") and key.endswith("__"):
                continue
            if key not in before or before.get(key) is not value:
                updates[key] = value
        return updates

    def _annotate_timeout(self, e: BaseException, code: str) -> None:
        """Annotate a TimeoutError with standard notes for observability."""
        try:
            # Only annotate exceptions that support add_note (3.11+)
            add_note = getattr(e, "add_note", None)
            if callable(add_note):
                add_note(f"Code execution timed out after {self.tla_timeout:.1f} seconds")
                add_note(f"Execution ID: {self.execution_id}")
                snippet = code[:160] + ("..." if len(code) > 160 else "")
                add_note(f"Code snippet: {snippet}")
        except Exception:
            # Never fail on annotation
            pass

    def _collect_safe_assigned_names(self, body: list[ast.stmt]) -> set[str]:
        """Collect simple identifiers safe for global declaration."""
        try:
            from .constants import ENGINE_INTERNALS as _engine_internals
        except Exception as _e:
            logger.debug(
                "ENGINE_INTERNALS import failed in _collect_safe_assigned_names; defaulting to empty set",
                error=str(_e),
                execution_id=self.execution_id,
            )
            _engine_internals = set()

        names: set[str] = set()
        for node in body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if not target.id.startswith("__") and target.id not in _engine_internals:
                            names.add(target.id)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    if not node.target.id.startswith("__"):
                        names.add(node.target.id)
            elif isinstance(node, ast.AugAssign):
                if isinstance(node.target, ast.Name):
                    names.add(node.target.id)
        return names

    def _resolve_attribute_base(self, node: ast.AST) -> str | None:
        """Resolve attribute/call/subscript chain to base name.

        Handles patterns like:
          - time.sleep() → base 'time'
          - requests.get() → base 'requests'
          - socket.socket().recv() → base 'socket'
          - Path('f').read_text() with from pathlib import Path → base 'Path'
        """
        visited = 0
        while True:
            visited += 1
            if visited > 50:
                # Safety guard to avoid pathological loops
                return None
            if isinstance(node, ast.Attribute):
                node = node.value
                continue
            if isinstance(node, ast.Call):
                # Peel one level: look at the called object
                node = node.func
                continue
            if isinstance(node, ast.Subscript):
                node = node.value
                continue
            break
        if isinstance(node, ast.Name):
            return node.id
        return None

    def _contains_await(self, node: ast.AST) -> bool:
        """Return True if the subtree contains an Await, skipping nested scopes.

        Traversal rules:
        - Search the body of the provided root node (even if it is a scope node itself).
        - Do not recurse into nested FunctionDef, AsyncFunctionDef, Lambda, or ClassDef encountered below.
        
        TODO(perf): If we expand def-rewrite scope or usage, consider a dedicated
        visitor with memoization to avoid repeated traversal patterns that can
        approach O(n^2) on deeply nested code.
        """
        def visit(n: ast.AST, barrier_for_scopes: bool) -> bool:
            if isinstance(n, ast.Await):
                return True
            if barrier_for_scopes and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                return False
            for child in ast.iter_child_nodes(n):
                # After the root, treat nested scopes as barriers
                if visit(child, True):
                    return True
            return False

        # Start without barriers so we inspect the immediate body of the root node
        return visit(node, False)

    def _should_transform_lambda(self, lam: ast.Lambda) -> bool:
        """Detect zero-arg lambda containing await."""
        # Zero-arg and contains await in body
        has_zero_args = (
            not lam.args.args
            and not lam.args.vararg
            and not lam.args.kwonlyargs
            and not lam.args.kwarg
        )
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
        new_assign = ast.Assign(
            targets=[ast.Name(id=target_name, ctx=ast.Store())],
            value=ast.Name(id=helper_name, ctx=ast.Load()),
        )
        ast.copy_location(new_assign, assign_stmt)

        return [async_def, new_assign]

    def _track_coroutine(self, coro: Any) -> None:
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
            execution_id=self.execution_id,
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
                    close = getattr(coro, "close", None)
                    if callable(close):
                        close()
                    cleaned += 1
                except Exception:
                    pass  # Already closed or running

        # Remove dead references
        for ref in dead_refs:
            self._pending_coroutines.discard(ref)

        return cleaned

    async def close(self) -> None:
        """Explicitly close the executor and clean up resources.

        This should be called when the executor is no longer needed.
        Alternatively, use AsyncExecutor as a context manager.
        """
        # Cleanup registered linecache entries (best-effort)
        # TODO(modes): Consider an opt-in mode to skip cleanup for post-mortem
        # traceback retention (e.g., keep a bounded set until process exit).
        try:
            for fname in list(self._fallback_linecache_keys.keys()):
                try:
                    if fname in linecache.cache:
                        del linecache.cache[fname]
                except Exception:
                    pass
            self._fallback_linecache_keys.clear()
        except Exception:
            pass
        cleaned = self.cleanup_coroutines()
        if cleaned > 0:
            logger.debug("cleaned_pending_coroutines", cleaned=cleaned)

    async def __aenter__(self) -> "AsyncExecutor":
        """Enter context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        """Exit context manager and clean up."""
        await self.close()
        return False

    # Fallback filename and linecache helpers
    def _make_fallback_filename(self, code: str) -> str:
        """Create a unique, human-readable virtual filename for fallback frames."""
        # Sanitize and truncate execution_id for readability
        exec_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(self.execution_id))[:20]
        short_hash = hashlib.md5(code.encode()).hexdigest()[:8]
        self._fallback_seq += 1
        seq = self._fallback_seq
        return f"<async_fallback:{exec_id}:{short_hash}:{seq}>"

    def _register_fallback_source(self, filename: str, code: str) -> None:
        """Register code in linecache and maintain per-executor LRU with optional capacity."""
        try:
            # TODO(perf): Consider caching splitlines() per fallback call to avoid
            # repeated splitlines on hot paths.
            linecache.cache[filename] = (
                len(code),
                None,
                code.splitlines(keepends=True),
                filename,
            )
        except Exception:
            # Best-effort; never fail execution due to cache registration
            return

        # Track in LRU and evict if necessary
        try:
            if filename in self._fallback_linecache_keys:
                # Move to end
                self._fallback_linecache_keys.move_to_end(filename)
            else:
                self._fallback_linecache_keys[filename] = None
            cap = self._fallback_linecache_max_size
            if isinstance(cap, int) and cap >= 0:
                while len(self._fallback_linecache_keys) > cap:
                    old, _ = self._fallback_linecache_keys.popitem(last=False)
                    try:
                        if old in linecache.cache:
                            del linecache.cache[old]
                            # TODO(obs): Consider logging LRU evictions at debug level
                            # for observability (evicted filename, current size).
                    except Exception:
                        pass
        except Exception:
            # Never let LRU maintenance cause failures
            pass
