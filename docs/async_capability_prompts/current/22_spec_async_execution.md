# Async Execution Specification

## Document Information
- **Version**: 1.0.0
- **Status**: Draft
- **Last Updated**: 2025-01-03
- **Classification**: Technical Specification

## Executive Summary

This specification defines the AsyncExecutor implementation for PyREPL3, providing top-level await support without IPython dependencies. The system leverages the `PyCF_ALLOW_TOP_LEVEL_AWAIT` compile flag (0x2000) to enable native async/await syntax at the module level, with automatic execution mode detection. An AST transformation wrapper exists only as a resilience fallback when direct compilation is unsuitable.

Promise‑first integration: The durable layer MUST prefer promise flows (`ctx.promise` + Protocol Bridge) for async work. Durable functions MUST NOT create or manage event loops; the executor/transport own a single loop per session.

## Phase 2 Updates

- Single‑loop policy is enforced end‑to‑end: only `Session` reads the transport; the protocol bridge resolves/rejects durable promises via message interceptors scheduled on the session loop.
- Durable functions are promise‑first and must not import or manage `asyncio` constructs — they yield on `ctx.promise` and delegate all transport work to the bridge.
- Correlation rules (local mode):
  - Execute → Result/Error: `exec:{execution_id}`; correlate responses on `execution_id`.
  - Input → InputResponse: `{execution_id}:input:{message.id}`; correlate on `input_id`.
- Error semantics: the bridge rejects on `ErrorMessage` with structured JSON; durable functions raise with `add_note` context.
- Timeout semantics: bridge rejections include context (`capability`, `execution_id`, `request_id`, `timeout`).

## Technical Foundation

### Core Discovery: PyCF_ALLOW_TOP_LEVEL_AWAIT

```python
# Critical compile flag that enables top-level await
PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x2000

# Usage pattern
base_flags = compile('', '', 'exec').co_flags
async_flags = base_flags | PyCF_ALLOW_TOP_LEVEL_AWAIT
compiled = compile(code, '<async>', 'exec', flags=async_flags)
```

### TLA Compile Decision Matrix (3.11–3.13)

- No flag, any mode: top‑level `await`/`async for`/`async with` → SyntaxError.
- Flag + `mode='exec'`: code object has `CO_COROUTINE`; evaluate to coroutine and await it.
- Flag + `mode='eval'`: evaluating the code object yields a coroutine that must be awaited to produce the value.
- Flag + `mode='single'`: interactive one‑liner semantics analogous to `exec`.

Preferred strategy: attempt compile‑first with the flag; only use the AST fallback wrapper when compilation raises an unrecoverable SyntaxError unrelated to ordinary top‑level async constructs.

### AST Fallback Policy (Phase 3)

- Minimal wrapper only; do not rewrite user code by default.
  - Insert an `async def __async_exec__():` wrapper.
  - Expression case: wrapper body is a single `return <expr>` preserving the original expression node; locations copied for PEP 657.
  - Statement case: wrapper body is the original statements in order, plus `return locals()` as the last statement. No reordering; no `global` declarations are inserted.
- Transforms gated and OFF by default:
  - def→async def (when body contains await): `enable_def_await_rewrite=False`.
  - zero‑arg lambda with await → helper async def: `enable_async_lambda_helper=False`.
 - Location mapping and tracebacks:
  - Parse with a human‑readable virtual filename using a stable prefix, e.g., `<async_fallback:...>`.
    The filename should be unique per execution (and source) to avoid collisions under concurrency.
  - Use `ast.copy_location` for inserted nodes and `ast.fix_missing_locations` before compile.
  - Register original source in `linecache.cache[filename]` so traceback frames display the user’s code lines. An engine may bound the number of registered entries (LRU) and clean them up on executor close.
- Namespace merge semantics:
  - Execute wrapper in the live globals mapping so functions bind `__globals__` to the session namespace.
  - After execution, merge locals first (from `locals()` result) and then compute/apply global diffs; preserve `ENGINE_INTERNALS` and skip `__async_exec__`, `asyncio`, and `__builtins__`.
  - With hoisting disabled, names assigned in the wrapper body are locals of the wrapper; functions defined in the same body may close over those locals rather than observing later global updates. This is acceptable under PR 3 and documented behavior.

#### Unexpected wrapper return type (statements path)

The wrapper for statement blocks ends with `return locals()`, so the expected return type is `dict`.
If a non-dict is returned (e.g., due to unforeseen execution anomalies), the engine:

- Emits a warning and skips merging any local variables to avoid corrupting the namespace.
- Still applies global diffs (e.g., if user code mutated `globals()` explicitly).
- Returns the original value and records it in result history (for diagnostic visibility).

Policy option (future deliberation): normalize this unexpected path by coercing the final result
to `None` to strictly maintain "statements return None" semantics. This would reduce visibility of
anomalous values in exchange for consistency. Any change to this policy should be documented and
reflected in tests.

### Migration Notes

- Hoisting removed: The engine no longer inserts `global` hoists in the fallback wrapper. Names assigned
  within the wrapper are locals of the wrapper function and can shadow module globals. Functions defined
  in the same wrapper body may close over those locals.
- Recommended patterns to preserve module-level semantics:
  - Use explicit `global <name>` in user code where appropriate.
  - Split code: assign globals first, then define functions in a separate execution/cell.
  - Avoid defining and consuming mutable globals within the same cell.
- Feature flags:
  - `enable_def_await_rewrite` and `enable_async_lambda_helper` remain OFF by default. Enabling them
    does not reintroduce hoisting; they are independent transforms available for advanced scenarios.

### Execution Mode Detection

```
Input Code Analysis
        ↓
┌──────────────────────────────┐
│   AST Parsing & Analysis     │
├──────────────────────────────┤
│  • Check for top-level await │
│  • Detect async functions    │
│  • Identify blocking I/O     │
│  • Analyze import patterns   │
└──────────────────────────────┘
        ↓
┌──────────────────────────────┐
│    Execution Mode Decision   │
├──────────────────────────────┤
│  Mode Selection:             │
│  • top_level_await          │
│  • async_def                │
│  • blocking_sync            │
│  • simple_sync              │
└──────────────────────────────┘
        ↓
    Route to Executor
```

## AsyncExecutor Implementation

### Class Architecture

```python
import ast
import asyncio
import sys
import types
import inspect
import weakref
from typing import Any, Dict, Optional, Set, Tuple
from enum import Enum
from resonate_sdk import Resonate

class ExecutionMode(Enum):
    """Execution modes for code analysis."""
    TOP_LEVEL_AWAIT = "top_level_await"
    ASYNC_DEF = "async_def"
    BLOCKING_SYNC = "blocking_sync"
    SIMPLE_SYNC = "simple_sync"
    UNKNOWN = "unknown"

class AsyncExecutor:
    """
    Custom async executor with top-level await support.
    
    Key Features:
    - Native top-level await using PyCF_ALLOW_TOP_LEVEL_AWAIT
    - Automatic execution mode detection
    - AST transformation fallback
    - Coroutine lifecycle management
    - Event loop coordination
    """
    
    # Critical discovery from investigation
    PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x2000
    
    # Blocking I/O indicators
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
        resonate: Resonate,
        namespace_manager: 'NamespaceManager',
        execution_id: str
    ):
        """
        Initialize AsyncExecutor.
        
        Args:
            resonate: Resonate instance for durability
            namespace_manager: Thread-safe namespace manager
            execution_id: Unique execution identifier
        """
        self.resonate = resonate
        self.namespace = namespace_manager
        self.execution_id = execution_id
        
        # Event loop management
        # SINGLE LOOP RULE: The session owns exactly one event loop used by
        # executor + transport. Upper layers MUST NOT create or run loops.
        # The loop is provided by the session/transport binding.
        self.loop = asyncio.get_running_loop()
        self.owns_loop = False
            
        # Coroutine tracking for cleanup
        self._pending_coroutines: Set[weakref.ref] = set()
        self._running_tasks: Set[asyncio.Task] = set()
        
        # AST cache for repeated executions
        self._ast_cache: Dict[str, ast.AST] = {}
        
        # Execution statistics
        self.stats = {
            "executions": 0,
            "mode_counts": {mode: 0 for mode in ExecutionMode},
            "errors": 0,
            "ast_transforms": 0
        }
```

### Execution Mode Analysis

```python
    def analyze_execution_mode(self, code: str) -> ExecutionMode:
        """
        Determine optimal execution mode for code.
        
        Analysis Steps:
        1. Try standard AST parsing
        2. Check for top-level await expressions
        3. Detect async function definitions
        4. Identify blocking I/O patterns
        5. Default to simple sync
        
        Returns:
            ExecutionMode enum value
        """
        try:
            # Try to parse code normally
            tree = ast.parse(code)
            
            # Store in cache for potential reuse
            code_hash = hash(code)
            self._ast_cache[code_hash] = tree
            
            # Check for top-level await (not inside function)
            for node in tree.body:
                if isinstance(node, ast.Expr):
                    if self._contains_await_at_top_level(node.value):
                        return ExecutionMode.TOP_LEVEL_AWAIT
                        
            # Check for async function definitions
            has_async_def = False
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    has_async_def = True
                    break
                    
            if has_async_def:
                return ExecutionMode.ASYNC_DEF
                
            # Check for blocking I/O patterns
            if self._contains_blocking_io(tree):
                return ExecutionMode.BLOCKING_SYNC
                
            # Default to simple sync
            return ExecutionMode.SIMPLE_SYNC
            
        except SyntaxError as e:
            # Code likely contains top-level await that doesn't parse
            if 'await' in str(e) or 'await' in code:
                return ExecutionMode.TOP_LEVEL_AWAIT
            # Unknown syntax error
            return ExecutionMode.UNKNOWN
    
    def _contains_await_at_top_level(self, node: ast.AST) -> bool:
        """
        Check if node contains await at module level.
        
        Recursively walks AST to find Await nodes that are
        not inside function definitions.
        """
        if isinstance(node, ast.Await):
            return True
            
        # Don't recurse into function definitions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
            
        # Check child nodes
        for child in ast.walk(node):
            if isinstance(child, ast.Await):
                return True
                
        return False
    
    def _contains_blocking_io(self, tree: ast.AST) -> bool:
        """
        Detect blocking I/O operations in code.
        
        Checks for:
        - Imports of blocking libraries
        - Calls to blocking functions
        - File operations without async
        """
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split('.')[0] in self.BLOCKING_IO_MODULES:
                        return True
                        
            # Check function calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.BLOCKING_IO_CALLS:
                        # Check if it's async version
                        if not self._is_in_async_context(node):
                            return True
                            
        return False
```

### Core Execution Methods

```python
    async def execute(self, code: str) -> Any:
        """
        Main execution entry point.
        
        Analyzes code and routes to appropriate execution method.
        Thread-safe and handles all execution modes.
        """
        self.stats["executions"] += 1
        
        # Analyze execution mode
        mode = self.analyze_execution_mode(code)
        self.stats["mode_counts"][mode] += 1
        
        try:
            if mode == ExecutionMode.TOP_LEVEL_AWAIT:
                return await self._execute_top_level_await(code)
                
            elif mode == ExecutionMode.ASYNC_DEF:
                return await self._execute_async_definitions(code)
                
            elif mode == ExecutionMode.BLOCKING_SYNC:
                return await self._execute_in_thread(code)
                
            elif mode == ExecutionMode.SIMPLE_SYNC:
                return self._execute_simple_sync(code)
                
            else:  # UNKNOWN
                # Attempt safe fallback
                return await self._execute_with_fallback(code)
                
        except Exception as e:
            self.stats["errors"] += 1
            # Store exception in namespace for debugging
            self.namespace.update_namespace(
                {'_last_exception': e},
                source_context='executor'
            )
            raise
        finally:
            # Cleanup any pending coroutines
            self._cleanup_pending_coroutines()
```

### Top-Level Await Implementation

#### Coroutine Lifecycle and Cancellation (PR 4)

- CoroutineManager (internal):
  - The executor maintains a lightweight internal manager that tracks exactly one “top‑level” execution at a time — the coroutine produced by TLA (eval/exec with `PyCF_ALLOW_TOP_LEVEL_AWAIT`) or by the AST wrapper (`__async_exec__`).
  - The coroutine is wrapped in an `asyncio.Task` and registered when execution begins; registration is cleared in `finally` regardless of success, error, or cancel.
  - The manager exposes a cooperative `cancel()` that targets only this top‑level task. It performs thread‑safe cancellation by scheduling `task.cancel()` via `loop.call_soon_threadsafe(...)` when invoked off the event‑loop thread. It does not enumerate or cancel user‑created background tasks.
  - Non‑blocking scheduling: off‑loop calls enqueue cancellation and return immediately without waiting; if the recorded loop is not running, the request is a no‑op.

- Public cancel API:
  - `AsyncExecutor.cancel_current(reason: str | None = None) -> bool` cancels the in‑flight top‑level task if present and not done; returns True when a cancel was issued, otherwise False (idempotent/no‑op when idle).
  - Cancellation is treated distinctly from errors. `CancelledError` is re‑raised after annotation and does not increment general error counters.

- Exception notes and telemetry:
  - On cancel/timeout, exceptions are annotated via `add_note` with keys: `execution_id`, `mode` (e.g., `tla_eval`, `tla_exec`, `ast_wrapper`), optional `cancel_reason`, optional `cancel_requested_at` timestamp, and a short `code_snippet` (≈160 chars).
  - Stats include: `cancels_requested`, `cancels_effective`, `cancels_noop`, `cancelled_errors`, and `coroutines_closed_on_cleanup` (last cleanup count).

- Cleanup semantics:
  - All top‑level executions exit through a `finally` that clears the manager and runs weakref‑based `cleanup_coroutines()`.
  - Cleanup closes any tracked coroutines (best‑effort) and discards references to ensure steady‑state `cleanup_coroutines() == 0` (helps detect leaks in tests).

Policy: cooperative cancellation is scoped strictly to the executor‑owned top‑level task. User code that spawns background tasks (e.g., via `asyncio.create_task`) is not cancelled or enumerated by the executor and remains the user’s responsibility to manage or clean up.

```python
    async def _execute_top_level_await(self, code: str) -> Any:
        """
        Execute code with top-level await support.
        
        Uses PyCF_ALLOW_TOP_LEVEL_AWAIT flag for direct compilation
        when possible, falls back to AST transformation if needed.
        """
        # Get base compile flags (compile-first preferred)
        base_flags = compile('', '', 'exec').co_flags
        
        # Add the magic flag for top-level await
        flags = base_flags | self.PyCF_ALLOW_TOP_LEVEL_AWAIT
        
        try:
            # Try direct compilation with flag
            compiled = compile(code, '<async_session>', 'exec', flags=flags)
            
            # Check if compiled code contains top-level await by inspecting CO_COROUTINE flag
            # This is more reliable than checking the result type
            import inspect
            is_coroutine_code = bool(inspect.CO_COROUTINE & compiled.co_flags)
            
            # Create execution namespace
            local_ns = {}
            global_ns = self.namespace.get_for_execution('async')
            
            # Execute compiled code
            coro_or_result = eval(compiled, global_ns, local_ns)
            
            # Handle result based on CO_COROUTINE flag and actual type
            if is_coroutine_code and inspect.iscoroutine(coro_or_result):
                # Track coroutine
                self._track_coroutine(coro_or_result)
                # Await the coroutine with timeout (Python 3.11+)
                async with asyncio.timeout(30):  # Default 30 second timeout
                    result = await coro_or_result
            else:
                result = coro_or_result
                
            # Update namespace with changes (merge, don't replace)
            self.namespace.update_namespace(local_ns, source_context='async')
            
            return result
            
        except SyntaxError:
            # Compilation failed, use AST transformation
            return await self._execute_with_ast_transform(code)
    
    def _track_coroutine(self, coro):
        """Track coroutine for cleanup."""
        # Use weak reference to avoid keeping coroutine alive
        self._pending_coroutines.add(weakref.ref(coro))
    
    def _cleanup_pending_coroutines(self):
        """Clean up any pending coroutines."""
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
                except:
                    pass  # Already closed or running
                    
        # Remove dead references
        for ref in dead_refs:
            self._pending_coroutines.discard(ref)
            
        return cleaned
```

### AST Transformation Fallback

```python
    async def _execute_with_ast_transform(self, code: str) -> Any:
        """
        Transform code for top-level await execution.
        
        Wraps code in async function only when direct compilation
        with PyCF_ALLOW_TOP_LEVEL_AWAIT fails.

        Narrow transform policy:
        - Do NOT mass-convert `def`→`async def` (semantics risk)
        - Zero-arg lambda→async helper is disabled by default
        - Preserve original ordering; apply locals-first then global diffs
        """
        self.stats["ast_transforms"] += 1
        
        # Parse code into AST
        tree = ast.parse(code)
        
        # Create async wrapper function
        async_wrapper = ast.AsyncFunctionDef(
            name='__async_exec__',
            args=ast.arguments(
                posonlyargs=[],
                args=[],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[]
            ),
            body=tree.body,
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
        global_ns = self.namespace.get_for_execution('async')
        exec(compiled, global_ns, local_ns)
        
        # Get and execute the async function
        async_func = local_ns['__async_exec__']
        result = await async_func()
        
        # Update namespace
        self.namespace.update_namespace(
            {k: v for k, v in local_ns.items() if k != '__async_exec__'},
            source_context='async'
        )
        
        return result

### Location Mapping (PEP 657)

- Use `ast.copy_location(new, old)` when replacing nodes to preserve start/end spans.
- Call `ast.fix_missing_locations(tree)` after modifications.
- Avoid `ast.increment_lineno` unless required; prefer not inserting prelude lines.
- Keep filenames stable; if using virtual filenames, register source in `linecache` for tracebacks.

### AST Coverage (3.11–3.13)

- Ensure traversal tolerates: `Match` and pattern subclasses (PEP 634), `TryStar` (PEP 654), `TypeAlias` and `type_params` on defs/classes (PEP 695). PEP 701 (f‑strings) needs no special handling.
- PEP 709 (comprehension inlining) affects symbol tables in 3.12+; do not mistake comprehension targets for real top‑level assignments during analysis.

### Caching Strategy

- Use a code‑object LRU cache keyed by `(source, mode, flags)` to skip re‑parse/compile for repeated inputs.
- Keep a small AST cache only if transforms are applied; compile‑first is faster when no transforms are needed.
```

### Thread-Based Execution for Blocking I/O

```python
    async def _execute_in_thread(self, code: str) -> Any:
        """
        Execute blocking code in thread pool.
        
        Preserves async context while running blocking I/O
        in separate thread to avoid blocking event loop.
        """
        import concurrent.futures
        
        # Get thread pool executor
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        
        # Create namespace copy for thread
        thread_namespace = self.namespace.get_for_execution('thread')
        
        def thread_execution():
            """Execute in thread context."""
            local_ns = {}
            
            try:
                # Compile and execute
                compiled = compile(code, '<thread_exec>', 'exec')
                exec(compiled, thread_namespace, local_ns)
                
                # Merge results
                thread_namespace.update(local_ns)
                
                # Extract result
                result = local_ns.get('_result') or local_ns.get('_')
                
                return {
                    'result': result,
                    'namespace': thread_namespace,
                    'locals': local_ns
                }
                
            except Exception as e:
                return {
                    'error': e,
                    'namespace': thread_namespace,
                    'locals': local_ns
                }
        
        # Run in thread pool
        future = self.loop.run_in_executor(executor, thread_execution)
        execution_result = await future
        
        # Handle result
        if 'error' in execution_result:
            raise execution_result['error']
            
        # Merge namespace changes
        self.namespace.merge_thread_results(
            execution_result['namespace'],
            thread_namespace
        )
        
        return execution_result['result']
```

### Event Loop Coordination

```python
class EventLoopCoordinator:
    """
    Coordinates event loop operations for async execution.
    
    Handles:
    - Event loop detection and creation
    - Task scheduling and cancellation
    - Message queue flushing
    - Async context management
    """
    
    def __init__(self, executor: AsyncExecutor):
        self.executor = executor
        self.message_queue = []
        self.in_async_context = False
        
    def ensure_event_loop(self) -> asyncio.AbstractEventLoop:
        """Ensure event loop exists and is running."""
        try:
            loop = asyncio.get_running_loop()
            self.in_async_context = True
            return loop
        except RuntimeError:
            # No running loop, check if one exists
            loop = asyncio.get_event_loop()
            if loop is None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            self.in_async_context = False
            return loop
    
    def queue_for_async(self, coro):
        """Queue coroutine for execution when in async context."""
        if self.in_async_context:
            # Can execute immediately
            return asyncio.create_task(coro)
        else:
            # Queue for later
            self.message_queue.append(coro)
            return None
    
    async def flush_queue(self):
        """Flush queued operations when entering async context."""
        if not self.message_queue:
            return
            
        # Now in async context
        self.in_async_context = True
        
        # Execute all queued coroutines
        tasks = []
        for coro in self.message_queue:
            task = asyncio.create_task(coro)
            tasks.append(task)
            
        # Wait for completion
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clear queue
        self.message_queue.clear()
        
        return results
```

### Coroutine Management

```python
class CoroutineManager:
    """
    Manages coroutine lifecycle and cleanup.
    
    Prevents coroutine leaks and ensures proper cleanup
    on execution boundaries.
    """
    
    def __init__(self):
        # Track coroutines with weak references
        self._coroutines: Set[weakref.ref] = set()
        self._tasks: Set[asyncio.Task] = set()
        
    def track_coroutine(self, coro):
        """Track a coroutine for lifecycle management."""
        self._coroutines.add(weakref.ref(coro))
        
    def track_task(self, task: asyncio.Task):
        """Track an asyncio task."""
        self._tasks.add(task)
        # Remove from set when done
        task.add_done_callback(self._tasks.discard)
        
    def cleanup(self) -> Dict[str, int]:
        """Clean up pending coroutines and tasks."""
        stats = {
            "coroutines_closed": 0,
            "tasks_cancelled": 0,
            "errors": 0
        }
        
        # Clean up coroutines
        dead_refs = []
        for coro_ref in self._coroutines:
            coro = coro_ref()
            if coro is None:
                dead_refs.append(coro_ref)
            else:
                try:
                    coro.close()
                    stats["coroutines_closed"] += 1
                except Exception:
                    stats["errors"] += 1
                    
        # Remove dead references
        for ref in dead_refs:
            self._coroutines.discard(ref)
            
        # Cancel pending tasks
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
                stats["tasks_cancelled"] += 1
                
        return stats
```

### Cancellation Support

```python
class ExecutionCancellation:
    """
    Provides cancellation support for running executions.
    
    Different strategies for sync vs async code.
    """
    
    def __init__(self, executor: AsyncExecutor):
        self.executor = executor
        self.cancelled = False
        self._cancel_callbacks = []
        
    def cancel_execution(self):
        """Cancel current execution."""
        self.cancelled = True
        
        # Cancel async tasks
        for task in self.executor._running_tasks:
            if not task.done():
                task.cancel()
                
        # Run cancellation callbacks
        for callback in self._cancel_callbacks:
            try:
                callback()
            except Exception:
                pass  # Ignore callback errors
                
    def check_cancelled(self):
        """Check if execution was cancelled."""
        if self.cancelled:
            raise asyncio.CancelledError("Execution cancelled")
            
    def add_cancel_callback(self, callback):
        """Add callback for cancellation."""
        self._cancel_callbacks.append(callback)
        
    @contextmanager
    def cancellable_execution(self):
        """Context manager for cancellable execution."""
        try:
            yield self
        finally:
            self.cancelled = False
            self._cancel_callbacks.clear()
```

## Resonate Integration

### Durable Execution Wrapper

```python
@resonate.register(
    name="async_execute",
    version="1.0.0",
    idempotent=True
)
def durable_async_execute(ctx, args):
    """
    Durable wrapper for async execution.
    
    Provides automatic recovery and state persistence.
    """
    code = args['code']
    execution_id = args['execution_id']
    
    # Get dependencies
    namespace_manager = ctx.get_dependency("namespace_manager")
    
    # Create executor instance
    executor = AsyncExecutor(
        resonate=ctx.resonate,
        namespace_manager=namespace_manager,
        execution_id=execution_id
    )
    
    # Analyze code
    mode = executor.analyze_execution_mode(code)
    
    # Checkpoint before execution
    yield ctx.checkpoint("pre_execution", {
        "code": code,
        "mode": mode.value,
        "namespace": namespace_manager.get_snapshot()
    })
    
    # Execute based on mode
    if mode == ExecutionMode.TOP_LEVEL_AWAIT:
        result = yield ctx.lfc(execute_top_level_await, {
            "executor": executor,
            "code": code
        })
    elif mode == ExecutionMode.BLOCKING_SYNC:
        result = yield ctx.lfc(execute_in_thread, {
            "executor": executor,
            "code": code
        })
    else:
        result = yield ctx.lfc(execute_standard, {
            "executor": executor,
            "code": code
        })
        
    # Checkpoint after execution
    yield ctx.checkpoint("post_execution", {
        "result": result,
        "namespace": namespace_manager.get_snapshot()
    })
    
    return result
```

## Error Handling

### Error Categories

```python
class ExecutionError(Exception):
    """Base exception for execution errors."""
    pass

class CompilationError(ExecutionError):
    """Code compilation failed."""
    pass

class AsyncContextError(ExecutionError):
    """Async context violation."""
    pass

class NamespaceError(ExecutionError):
    """Namespace operation error."""
    pass

class CancellationError(ExecutionError):
    """Execution was cancelled."""
    pass
```

### Error Recovery Strategies

```python
class ErrorRecovery:
    """Implements error recovery strategies."""
    
    @staticmethod
    def handle_compilation_error(e: SyntaxError, code: str) -> str:
        """
        Attempt to fix common compilation errors.
        
        Strategies:
        - Add missing colons
        - Fix indentation
        - Convert print statements
        """
        # Implementation of auto-fix strategies
        pass
        
    @staticmethod
    def handle_async_context_error(e: RuntimeError) -> bool:
        """
        Handle async context errors.
        
        Returns True if recovered, False otherwise.
        """
        if "no running event loop" in str(e):
            # Create new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return True
        return False
```

## Performance Optimizations

### Compilation Caching

```python
class CompilationCache:
    """Cache compiled code objects."""
    
    def __init__(self, max_size: int = 1000):
        self.cache = {}
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        
    def get_compiled(
        self,
        code: str,
        filename: str,
        mode: str,
        flags: int
    ) -> Optional[types.CodeType]:
        """Get compiled code from cache."""
        key = (hash(code), filename, mode, flags)
        
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
            
        self.misses += 1
        return None
        
    def store_compiled(
        self,
        code: str,
        filename: str,
        mode: str,
        flags: int,
        compiled: types.CodeType
    ):
        """Store compiled code in cache."""
        if len(self.cache) >= self.max_size:
            # Evict oldest entry (simple FIFO)
            self.cache.pop(next(iter(self.cache)))
            
        key = (hash(code), filename, mode, flags)
        self.cache[key] = compiled
```

### AST Optimization

```python
class ASTOptimizer:
    """Optimize AST before compilation."""
    
    def optimize(self, tree: ast.AST) -> ast.AST:
        """
        Apply AST optimizations.
        
        Optimizations:
        - Constant folding
        - Dead code elimination
        - Common subexpression elimination
        """
        # Apply optimization passes
        tree = self._constant_folding(tree)
        tree = self._dead_code_elimination(tree)
        
        # Fix locations after modifications
        ast.fix_missing_locations(tree)
        
        return tree
```

## Testing Strategy

### Unit Tests

```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_top_level_await_flag():
    """Test PyCF_ALLOW_TOP_LEVEL_AWAIT flag works."""
    code = "import asyncio; result = await asyncio.sleep(0, 'test')"
    
    # Create executor
    resonate = Resonate.local()
    namespace_manager = NamespaceManager(resonate)
    executor = AsyncExecutor(resonate, namespace_manager, "test-1")
    
    # Execute with top-level await
    result = await executor.execute(code)
    
    assert result == 'test'
    assert executor.stats["mode_counts"][ExecutionMode.TOP_LEVEL_AWAIT] == 1

@pytest.mark.asyncio
async def test_execution_mode_detection():
    """Test correct execution mode detection."""
    test_cases = [
        ("await asyncio.sleep(0)", ExecutionMode.TOP_LEVEL_AWAIT),
        ("async def foo(): pass", ExecutionMode.ASYNC_DEF),
        ("import requests; r = requests.get('url')", ExecutionMode.BLOCKING_SYNC),
        ("x = 1 + 1", ExecutionMode.SIMPLE_SYNC)
    ]
    
    executor = AsyncExecutor(Resonate.local(), NamespaceManager(), "test")
    
    for code, expected_mode in test_cases:
        mode = executor.analyze_execution_mode(code)
        assert mode == expected_mode

@pytest.mark.asyncio
async def test_namespace_preservation():
    """Test namespace is preserved across executions."""
    resonate = Resonate.local()
    namespace_manager = NamespaceManager(resonate)
    executor = AsyncExecutor(resonate, namespace_manager, "test-2")
    
    # First execution
    await executor.execute("x = 42")
    
    # Second execution using previous variable
    result = await executor.execute("result = x * 2")
    
    # Check namespace contains both
    namespace = namespace_manager.namespace
    assert namespace.get('x') == 42
    assert namespace.get('result') == 84

@pytest.mark.asyncio
async def test_coroutine_cleanup():
    """Test coroutines are properly cleaned up."""
    executor = AsyncExecutor(Resonate.local(), NamespaceManager(), "test-3")
    
    # Track initial state
    initial_coros = len(executor._pending_coroutines)
    
    # Execute code that creates coroutines
    await executor.execute("import asyncio; coro = asyncio.sleep(0)")
    
    # Cleanup should occur
    assert len(executor._pending_coroutines) == initial_coros
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_mixed_execution_modes():
    """Test mixed sync and async execution."""
    resonate = Resonate.local()
    namespace_manager = NamespaceManager(resonate)
    executor = AsyncExecutor(resonate, namespace_manager, "test-4")
    
    # Mix of execution modes
    await executor.execute("x = 1")  # Simple sync
    await executor.execute("async def double(n): return n * 2")  # Async def
    await executor.execute("y = await double(x)")  # Top-level await
    
    assert namespace_manager.namespace.get('y') == 2

@pytest.mark.asyncio
async def test_error_recovery():
    """Test error recovery mechanisms."""
    executor = AsyncExecutor(Resonate.local(), NamespaceManager(), "test-5")
    
    # Syntax error should not crash executor
    with pytest.raises(SyntaxError):
        await executor.execute("invalid python code {[}")
        
    # Executor should still work
    result = await executor.execute("1 + 1")
    assert result == 2
```

### Performance Tests

```python
@pytest.mark.benchmark
async def test_execution_performance():
    """Benchmark execution performance."""
    executor = AsyncExecutor(Resonate.local(), NamespaceManager(), "perf-1")
    
    # Measure simple execution
    start = time.time()
    for _ in range(1000):
        await executor.execute("x = 1 + 1")
    simple_time = time.time() - start
    
    # Measure async execution
    start = time.time()
    for _ in range(100):
        await executor.execute("await asyncio.sleep(0)")
    async_time = time.time() - start
    
    # Assert performance targets
    assert simple_time < 1.0  # < 1ms per execution
    assert async_time < 1.0   # < 10ms per async execution
```

## Configuration

### Executor Configuration

```python
class ExecutorConfig:
    """Configuration for AsyncExecutor."""
    
    # Execution limits
    max_execution_time: float = 30.0
    max_memory_usage: int = 512 * 1024 * 1024  # 512MB
    max_coroutines: int = 1000
    
    # Optimization settings
    enable_compilation_cache: bool = True
    enable_ast_optimization: bool = True
    cache_size: int = 1000
    
    # Safety settings
    allow_imports: bool = True
    allowed_modules: Set[str] = None  # None means all
    denied_modules: Set[str] = {'os', 'sys', 'subprocess'}
    
    # Debug settings
    trace_execution: bool = False
    collect_stats: bool = True
    verbose_errors: bool = True
```

## Monitoring and Metrics

### Execution Metrics

```python
class ExecutionMetrics:
    """Collect and report execution metrics."""
    
    def __init__(self):
        self.metrics = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "execution_times": [],
            "mode_distribution": {},
            "cache_hit_rate": 0.0,
            "ast_transforms": 0
        }
        
    def record_execution(
        self,
        mode: ExecutionMode,
        duration: float,
        success: bool
    ):
        """Record execution metrics."""
        self.metrics["total_executions"] += 1
        
        if success:
            self.metrics["successful_executions"] += 1
        else:
            self.metrics["failed_executions"] += 1
            
        self.metrics["execution_times"].append(duration)
        
        mode_key = mode.value
        self.metrics["mode_distribution"][mode_key] = \
            self.metrics["mode_distribution"].get(mode_key, 0) + 1
```

## Security Considerations

### Import Control

```python
class ImportController:
    """Control module imports for security."""
    
    def __init__(self, config: ExecutorConfig):
        self.config = config
        self.original_import = __builtins__.__import__
        
    def controlled_import(
        self,
        name,
        globals=None,
        locals=None,
        fromlist=(),
        level=0
    ):
        """Controlled import function."""
        # Check if imports are allowed
        if not self.config.allow_imports:
            raise ImportError("Imports are disabled")
            
        # Check denied modules
        if self.config.denied_modules and name in self.config.denied_modules:
            raise ImportError(f"Import of {name} is denied")
            
        # Check allowed modules
        if self.config.allowed_modules and name not in self.config.allowed_modules:
            raise ImportError(f"Import of {name} is not allowed")
            
        # Perform actual import
        return self.original_import(name, globals, locals, fromlist, level)
```

## Future Enhancements

### Planned Features

1. **JIT Compilation**
   - Integrate with PyPy JIT
   - Profile-guided optimization
   - Hot code detection

2. **Advanced AST Analysis**
   - Data flow analysis
   - Type inference
   - Dead code elimination

3. **Distributed Execution**
   - Code splitting for parallelization
   - Remote execution support
   - Result aggregation

4. **Enhanced Debugging**
   - Step-through debugging
   - Breakpoint support
   - Variable inspection

## Appendices

### A. PyCF_ALLOW_TOP_LEVEL_AWAIT Details

The `PyCF_ALLOW_TOP_LEVEL_AWAIT` flag (0x2000) was introduced in Python 3.8 to enable top-level await in interactive environments. Key characteristics:

**How It Works:**
- Allows `await` expressions at module level in interactive contexts
- When used, compiled code object has `CO_COROUTINE` flag set in `co_flags`
- Returns coroutine object that must be awaited (not immediate execution)
- Check with: `bool(inspect.CO_COROUTINE & compiled.co_flags)`

**Critical Limitations:**
- **Cannot be used in importable modules** - only works in:
  - Interactive environments (REPL, IPython, Jupyter)
  - Explicitly compiled code with the flag
  - Scripts run with `python -m asyncio`
- Standard module imports will still raise SyntaxError with top-level await
- Requires active event loop to execute the resulting coroutine

**Best Practice Pattern:**
```python
compiled = compile(code, '<exec>', 'exec', flags=flags)
if inspect.CO_COROUTINE & compiled.co_flags:
    result = eval(compiled, globals, locals)
    result = await result  # Must await the coroutine
```

### B. AST Node Reference

Common AST nodes for async code:
- `ast.Await`: Await expression
- `ast.AsyncFunctionDef`: Async function definition
- `ast.AsyncFor`: Async for loop
- `ast.AsyncWith`: Async with statement

### C. Modern Python 3.11+ Async Features

**Structured Concurrency with TaskGroup:**
```python
async def execute_concurrent_tasks(self, tasks: list) -> list:
    """Execute multiple tasks with structured concurrency (Python 3.11+)."""
    results = []
    exceptions = []
    
    async with asyncio.TaskGroup() as tg:
        for task_code in tasks:
            task = tg.create_task(self.execute(task_code))
            results.append(task)
    
    # All tasks complete or all are cancelled on error
    # Exceptions are grouped in an ExceptionGroup
    return [await r for r in results]
```

**Timeout Management (Python 3.11+):**
```python
# Preferred over asyncio.wait_for() in Python 3.11+
async with asyncio.timeout(30):  # 30 second timeout
    result = await coroutine
```

**Enhanced Error Context (Python 3.11+):**
```python
try:
    result = await self.execute(code)
except Exception as e:
    # Add execution context using exception notes
    e.add_note(f"Execution ID: {self.execution_id}")
    e.add_note(f"Execution mode: {mode.value}")
    e.add_note(f"Session: {self.session_id}")
    raise
```

### D. Event Loop Considerations

Event loop management strategies:
- Reuse existing loop when possible (`asyncio.get_running_loop()`)
- Create new loop only when necessary
- Use `asyncio.timeout()` for execution timeouts (3.11+)
- Handle nested loop scenarios with care
- Clean up pending coroutines on executor destruction
