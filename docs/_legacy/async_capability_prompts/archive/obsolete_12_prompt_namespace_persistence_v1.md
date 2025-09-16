# Namespace Persistence Across Async/Sync Boundaries Planning Prompt

## Your Mission

You are tasked with ensuring namespace persistence works correctly across async and sync execution contexts. With the new async-first model, code may execute in async context, thread pool, or direct sync-in-async mode. The namespace must remain consistent and accessible across all these boundaries, with proper handling of async functions, coroutines, and capability injections.

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. The Challenge
- **Multiple Execution Contexts**: Async event loop, thread pool, sync-in-async
- **Namespace Sharing**: Same namespace accessed from different contexts
- **Async Functions**: Must persist and be callable across executions
- **Coroutines**: Handle unawaited coroutines in namespace
- **Capabilities**: Injected async capabilities must work everywhere

### 2. Current Issues
- **Context Switching**: Namespace changes in thread might not reflect in async
- **Coroutine Leaks**: Unawaited coroutines left in namespace
- **Async Function Calls**: Can't call async functions from sync context directly
- **Capability Persistence**: Async capabilities need special handling

### 3. Required Behaviors
- Variables defined in one context visible in all contexts
- Functions (sync and async) callable appropriately
- Capabilities remain available across executions
- Coroutines properly managed (awaited or cleaned up)

## Planning Methodology

### Phase 1: Analysis (30% effort)
<context_gathering>
Goal: Understand namespace synchronization challenges
Stop when: You know how Python handles namespace across contexts
Depth: Study globals(), locals(), async function storage, coroutine lifecycle
</context_gathering>

Investigate:
1. How Python namespaces work across threads
2. Async function storage in namespace
3. Coroutine lifecycle management
4. Thread-safe namespace operations

### Phase 2: Solution Design (50% effort)

**Enhanced NamespaceManager for Async:**

```python
# Extensions to src/subprocess/namespace.py
import asyncio
import threading
from typing import Any, Dict, Optional, Union
import inspect

class AsyncNamespaceManager(NamespaceManager):
    """Namespace manager with async/sync boundary handling."""
    
    def __init__(self):
        super().__init__()
        self._namespace_lock = threading.RLock()  # Thread-safe access
        self._async_functions: Dict[str, Any] = {}  # Track async functions
        self._pending_coroutines: Dict[str, asyncio.Task] = {}  # Track coroutines
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the event loop for async operations."""
        self._loop = loop
    
    @property
    def namespace(self) -> Dict[str, Any]:
        """Thread-safe namespace access."""
        with self._namespace_lock:
            return self._namespace
    
    def update_namespace(self, updates: Dict[str, Any], source_context: str = "unknown"):
        """Update namespace from any context.
        
        Args:
            updates: Dictionary of updates
            source_context: Where update originates (async/thread/sync)
        """
        with self._namespace_lock:
            for key, value in updates.items():
                # Track async functions specially
                if inspect.iscoroutinefunction(value):
                    self._async_functions[key] = value
                    # Create wrapper for sync contexts
                    self._namespace[key] = self._create_async_wrapper(value)
                
                # Handle coroutines (unawaited async calls)
                elif inspect.iscoroutine(value):
                    # Auto-schedule coroutine as task
                    if self._loop:
                        task = self._loop.create_task(value)
                        self._pending_coroutines[key] = task
                        self._namespace[key] = task
                    else:
                        # Store for later scheduling
                        self._namespace[key] = value
                
                # Regular values
                else:
                    self._namespace[key] = value
            
            logger.debug(
                "Namespace updated",
                source_context=source_context,
                keys_updated=list(updates.keys()),
                async_functions=list(self._async_functions.keys())
            )
    
    def _create_async_wrapper(self, async_func: Any) -> Any:
        """Create wrapper that can be called from sync context."""
        
        def sync_wrapper(*args, **kwargs):
            """Wrapper that creates coroutine for later awaiting."""
            coro = async_func(*args, **kwargs)
            
            # If we have event loop, schedule it
            if self._loop and self._loop.is_running():
                task = self._loop.create_task(coro)
                return task
            else:
                # Return coroutine for manual handling
                return coro
        
        # Preserve function metadata
        sync_wrapper.__name__ = async_func.__name__
        sync_wrapper.__doc__ = async_func.__doc__
        sync_wrapper.__wrapped__ = async_func
        sync_wrapper._is_async = True
        
        return sync_wrapper
    
    async def await_pending_coroutines(self):
        """Await all pending coroutines in namespace."""
        if not self._pending_coroutines:
            return
        
        results = {}
        for key, task in list(self._pending_coroutines.items()):
            try:
                result = await task
                results[key] = result
                # Update namespace with result
                with self._namespace_lock:
                    self._namespace[key] = result
            except Exception as e:
                logger.error(f"Error awaiting coroutine {key}: {e}")
            finally:
                del self._pending_coroutines[key]
        
        return results
    
    def cleanup_coroutines(self):
        """Cancel and cleanup pending coroutines."""
        for key, task in self._pending_coroutines.items():
            if not task.done():
                task.cancel()
        self._pending_coroutines.clear()
```

**Execution Context Bridge:**

```python
# src/subprocess/context_bridge.py
class ExecutionContextBridge:
    """Bridges namespace across execution contexts."""
    
    def __init__(self, namespace_manager: AsyncNamespaceManager):
        self.namespace = namespace_manager
        self._context_stack = []
    
    async def execute_in_async(self, code: str) -> Any:
        """Execute in async context."""
        # Push context
        self._push_context('async')
        
        try:
            # Create local namespace that references main
            local_ns = {}
            global_ns = self.namespace.namespace
            
            # Execute code
            exec(compile(code, '<async>', 'exec'), global_ns, local_ns)
            
            # Handle any coroutines created
            for key, value in local_ns.items():
                if inspect.iscoroutine(value):
                    local_ns[key] = await value
            
            # Update main namespace
            self.namespace.update_namespace(local_ns, 'async')
            
            # Check for return value
            return local_ns.get('__result__')
            
        finally:
            self._pop_context()
    
    def execute_in_thread(self, code: str) -> Any:
        """Execute in thread context."""
        # Push context
        self._push_context('thread')
        
        try:
            # Thread execution uses namespace directly
            local_ns = {}
            global_ns = self.namespace.namespace
            
            # Execute code
            exec(compile(code, '<thread>', 'exec'), global_ns, local_ns)
            
            # Update namespace (thread-safe)
            self.namespace.update_namespace(local_ns, 'thread')
            
            return local_ns.get('__result__')
            
        finally:
            self._pop_context()
    
    async def execute_sync_in_async(self, code: str) -> Any:
        """Execute sync code in async context."""
        # Push context
        self._push_context('sync_in_async')
        
        try:
            # Similar to async but no await handling needed
            local_ns = {}
            global_ns = self.namespace.namespace
            
            # Execute code
            exec(compile(code, '<sync>', 'exec'), global_ns, local_ns)
            
            # Update namespace
            self.namespace.update_namespace(local_ns, 'sync_in_async')
            
            return local_ns.get('__result__')
            
        finally:
            self._pop_context()
    
    def _push_context(self, context_type: str):
        """Push execution context onto stack."""
        self._context_stack.append({
            'type': context_type,
            'timestamp': time.time(),
            'namespace_snapshot': len(self.namespace.namespace)
        })
    
    def _pop_context(self):
        """Pop execution context from stack."""
        if self._context_stack:
            context = self._context_stack.pop()
            logger.debug(f"Exited {context['type']} context")
```

**Namespace Synchronization:**

```python
# src/subprocess/namespace_sync.py
class NamespaceSynchronizer:
    """Ensures namespace consistency across contexts."""
    
    def __init__(self, namespace_manager: AsyncNamespaceManager):
        self.namespace = namespace_manager
        self._sync_lock = asyncio.Lock()
    
    async def sync_after_execution(self, context: str):
        """Synchronize namespace after execution in any context."""
        async with self._sync_lock:
            # Await any pending coroutines
            await self.namespace.await_pending_coroutines()
            
            # Clean up completed tasks
            self._cleanup_completed_tasks()
            
            # Validate namespace consistency
            self._validate_namespace()
    
    def _cleanup_completed_tasks(self):
        """Remove completed tasks from namespace."""
        with self.namespace._namespace_lock:
            for key, value in list(self.namespace.namespace.items()):
                if isinstance(value, asyncio.Task) and value.done():
                    try:
                        # Replace task with result
                        result = value.result()
                        self.namespace.namespace[key] = result
                    except Exception as e:
                        # Replace task with exception
                        self.namespace.namespace[key] = e
    
    def _validate_namespace(self):
        """Validate namespace consistency."""
        issues = []
        
        with self.namespace._namespace_lock:
            for key, value in self.namespace.namespace.items():
                # Check for unhandled coroutines
                if inspect.iscoroutine(value):
                    issues.append(f"Unawaited coroutine: {key}")
                
                # Check for cancelled tasks
                if isinstance(value, asyncio.Task) and value.cancelled():
                    issues.append(f"Cancelled task: {key}")
        
        if issues:
            logger.warning("Namespace issues detected", issues=issues)
```

### Phase 3: Risk Assessment (20% effort)

- **Risk**: Race conditions in namespace updates
  - Mitigation: Thread locks, atomic operations
  
- **Risk**: Coroutine leaks
  - Mitigation: Automatic cleanup, tracking
  
- **Risk**: Deadlocks between contexts
  - Mitigation: Timeout, careful lock ordering

## Output Requirements

Your implementation must include:

### 1. Executive Summary
- How namespace persistence works across contexts
- Handling of async functions and coroutines
- Thread safety guarantees
- Performance implications

### 2. Test Cases

```python
async def test_namespace_across_contexts():
    """Test namespace persistence across execution contexts."""
    namespace = AsyncNamespaceManager()
    executor = AsyncExecutor(namespace, transport, "test")
    
    # Define variable in async context
    await executor.execute("x = 42")
    
    # Access from thread context
    result = await executor.execute_in_thread("y = x * 2; y")
    assert result == 84
    
    # Access from sync-in-async context
    result = await executor.execute_sync_in_async("z = x + y; z")
    assert result == 126

async def test_async_function_persistence():
    """Test async functions persist in namespace."""
    namespace = AsyncNamespaceManager()
    executor = AsyncExecutor(namespace, transport, "test")
    
    # Define async function
    code1 = """
async def fetch_data():
    await asyncio.sleep(0.1)
    return 'data'
"""
    await executor.execute(code1)
    
    # Call from another execution
    code2 = "result = await fetch_data(); result"
    result = await executor.execute(code2)
    assert result == 'data'

async def test_coroutine_cleanup():
    """Test coroutines are properly managed."""
    namespace = AsyncNamespaceManager()
    
    # Create unawaited coroutine
    code = """
async def slow_op():
    await asyncio.sleep(1)
    return 'done'

task = slow_op()  # Not awaited
"""
    await executor.execute(code)
    
    # Check it's tracked
    assert 'task' in namespace._pending_coroutines
    
    # Await pending
    results = await namespace.await_pending_coroutines()
    assert results['task'] == 'done'
```

## Calibration

<context_gathering>
- Search depth: MEDIUM (synchronization patterns)
- Maximum tool calls: 15-20
- Early stop: When thread safety is understood
</context_gathering>

## Non-Negotiables

1. **Thread safety**: No race conditions
2. **No coroutine leaks**: All coroutines tracked
3. **Consistency**: Same namespace view from all contexts
4. **Performance**: Minimal synchronization overhead

## Success Criteria

- [ ] Variables persist across all execution contexts
- [ ] Async functions callable appropriately
- [ ] Coroutines properly managed
- [ ] Thread-safe namespace operations
- [ ] No memory leaks from coroutines

## Additional Guidance

- Use threading.RLock for reentrant locking
- Consider weakref for coroutine tracking
- Look at contextvars for context-local state
- Study asyncio.create_task for coroutine scheduling
- Document which operations are atomic