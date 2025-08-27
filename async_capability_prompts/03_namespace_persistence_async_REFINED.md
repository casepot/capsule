# Namespace Persistence Across Async/Sync Boundaries Planning Prompt (REFINED)

## Your Mission

You are tasked with ensuring namespace persistence works correctly across async and sync execution contexts. Based on investigation, the critical insight is: **NEVER replace the namespace dictionary entirely** - this causes KeyError failures. Always merge updates while preserving execution engine internals.

## Context Gathering Requirements

### 1. Problem History (CRITICAL DISCOVERY)
- **IPython Namespace Failure**: Replacing `user_ns` caused `KeyError: '_oh'`
- **Root Cause**: Execution engines maintain internal variables in namespace
- **Key Lesson**: Must preserve engine internals (_oh, Out, In, _, __, ___)
- **Solution**: Always merge updates, never replace

### 2. Threading Complexity (NEW INSIGHT)  
- **Issue**: Namespace accessed from event loop AND thread pool
- **Discovery**: Simple dict not thread-safe across contexts
- **Requirement**: Need RLock for all namespace operations
- **Pattern**: Copy for thread execution, merge results back

### 3. Coroutine Management (INVESTIGATION FINDING)
- **Problem**: Unawaited coroutines leak in namespace
- **IPython Approach**: Complex coroutine tracking
- **Our Solution**: Simpler - track and cleanup on execution boundary

## Planning Methodology

### Phase 1: Analysis (20% effort - REDUCED, problem understood)
<context_gathering>
Goal: Understand Python's namespace sharing mechanics
Stop when: Thread-safe update pattern is clear
Depth: Focus on threading.RLock and dict.update() semantics
</context_gathering>

### Phase 2: Solution Design (60% effort - FOCUSED on robustness)

**Thread-Safe Namespace Manager (REFINED):**

```python
# src/subprocess/namespace.py - ENHANCED
import asyncio
import threading
import weakref
from typing import Any, Dict, Set, Optional
import inspect

class AsyncNamespaceManager:
    """Namespace manager with critical safety improvements."""
    
    def __init__(self):
        # CRITICAL: Thread-safe access
        self._namespace_lock = threading.RLock()
        
        # The actual namespace
        self._namespace: Dict[str, Any] = {
            "__name__": "__main__",
            "__doc__": None,
            "__package__": None,
            "__loader__": None,
            "__spec__": None,
            "__annotations__": {},
            "__builtins__": __builtins__,
        }
        
        # Track async constructs
        self._async_functions: Dict[str, Any] = {}
        self._pending_coroutines: weakref.WeakSet = weakref.WeakSet()
        
        # CRITICAL: Preserve engine internals
        self._preserved_keys: Set[str] = set()
        self._init_engine_internals()
    
    def _init_engine_internals(self):
        """Initialize engine internals that must be preserved."""
        # These are what IPython uses - we preserve similar
        engine_internals = {
            '_': None,           # Last result
            '__': None,          # Second to last
            '___': None,         # Third to last  
            '_exit_code': 0,     # Last exit code
            '_exception': None,  # Last exception
        }
        
        with self._namespace_lock:
            self._namespace.update(engine_internals)
            self._preserved_keys.update(engine_internals.keys())
    
    @property
    def namespace(self) -> Dict[str, Any]:
        """Get namespace snapshot for reading."""
        with self._namespace_lock:
            # Return a snapshot to prevent modification
            return dict(self._namespace)
    
    def get_for_execution(self, execution_context: str) -> Dict[str, Any]:
        """Get namespace for code execution."""
        with self._namespace_lock:
            if execution_context == 'thread':
                # For thread execution, return a copy
                return self._namespace.copy()
            else:
                # For async execution, return direct reference
                # (async is single-threaded within event loop)
                return self._namespace
    
    def update_namespace(
        self,
        updates: Dict[str, Any],
        source_context: str = "unknown"
    ) -> None:
        """CRITICAL: Merge updates, never replace."""
        
        with self._namespace_lock:
            # Filter out None and empty values
            filtered_updates = {}
            
            for key, value in updates.items():
                # Skip engine internals from updates
                if key in self._preserved_keys and source_context != "engine":
                    continue
                
                # Handle coroutines
                if inspect.iscoroutine(value):
                    # Track for cleanup but don't store directly
                    self._pending_coroutines.add(value)
                    # Store a placeholder
                    filtered_updates[key] = f"<coroutine {key}>"
                    continue
                
                # Handle async functions
                if inspect.iscoroutinefunction(value):
                    self._async_functions[key] = value
                    # Create callable wrapper
                    filtered_updates[key] = self._create_sync_wrapper(value)
                    continue
                
                # Normal values
                filtered_updates[key] = value
            
            # CRITICAL: Use update(), never assign
            self._namespace.update(filtered_updates)
            
            # Update engine internals if execution completed
            if source_context in ['async', 'thread']:
                self._update_result_history(filtered_updates)
    
    def _update_result_history(self, updates: Dict[str, Any]):
        """Update result history like IPython but simpler."""
        # Look for a result value
        result = updates.get('_result') or updates.get('__result__')
        
        if result is not None:
            with self._namespace_lock:
                # Shift history
                self._namespace['___'] = self._namespace.get('__')
                self._namespace['__'] = self._namespace.get('_')
                self._namespace['_'] = result
    
    def _create_sync_wrapper(self, async_func: Any) -> Any:
        """Create wrapper for async function callable from sync."""
        
        def wrapper(*args, **kwargs):
            """Wrapper that returns coroutine."""
            coro = async_func(*args, **kwargs)
            # Track it
            self._pending_coroutines.add(coro)
            return coro
        
        wrapper.__name__ = async_func.__name__
        wrapper.__doc__ = async_func.__doc__
        wrapper._is_async_wrapper = True
        
        return wrapper
    
    def cleanup_coroutines(self) -> int:
        """Clean up pending coroutines."""
        cleaned = 0
        
        # Get coroutines to clean (weak refs may be gone)
        to_clean = list(self._pending_coroutines)
        
        for coro in to_clean:
            try:
                coro.close()
                cleaned += 1
            except:
                pass  # Already closed or running
        
        self._pending_coroutines.clear()
        return cleaned
    
    def merge_thread_results(
        self,
        thread_namespace: Dict[str, Any],
        original_namespace: Dict[str, Any]
    ) -> None:
        """Merge results from thread execution."""
        
        # Calculate changes
        changes = {}
        for key, value in thread_namespace.items():
            if key not in original_namespace or original_namespace[key] != value:
                changes[key] = value
        
        # Apply changes
        self.update_namespace(changes, source_context='thread')
```

**Execution Context Bridge (REFINED):**

```python
# src/subprocess/context_bridge.py
class ExecutionContextBridge:
    """Safely bridge namespace across execution contexts."""
    
    def __init__(self, namespace_manager: AsyncNamespaceManager):
        self.namespace = namespace_manager
        self._execution_id = None
    
    async def execute_in_async(self, code: str, execution_id: str) -> Any:
        """Execute in async context with namespace safety."""
        self._execution_id = execution_id
        
        # Get namespace reference (not copy for async)
        ns = self.namespace.get_for_execution('async')
        
        # Local namespace for this execution
        local_ns = {}
        
        try:
            # Compile and execute
            compiled = compile(code, '<async>', 'exec')
            exec(compiled, ns, local_ns)
            
            # Handle any coroutines created
            for key, value in list(local_ns.items()):
                if inspect.iscoroutine(value):
                    local_ns[key] = await value
            
            # Merge back (not replace!)
            self.namespace.update_namespace(local_ns, 'async')
            
            # Check for result
            return local_ns.get('_result')
            
        finally:
            # Cleanup any pending coroutines
            self.namespace.cleanup_coroutines()
    
    def execute_in_thread(self, code: str, execution_id: str) -> Any:
        """Execute in thread with namespace safety."""
        self._execution_id = execution_id
        
        # Get namespace copy for thread
        ns_copy = self.namespace.get_for_execution('thread')
        original_ns = ns_copy.copy()
        
        # Local namespace
        local_ns = {}
        
        try:
            # Execute in thread's copy
            compiled = compile(code, '<thread>', 'exec')
            exec(compiled, ns_copy, local_ns)
            
            # Merge changes back to main namespace
            ns_copy.update(local_ns)
            self.namespace.merge_thread_results(ns_copy, original_ns)
            
            return local_ns.get('_result')
            
        except Exception as e:
            # Store exception in namespace
            self.namespace.update_namespace(
                {'_exception': e},
                source_context='engine'
            )
            raise
```

### Phase 3: Risk Assessment (20% effort)

**Critical Risks from Investigation:**

1. **Namespace Replacement Error**
   - **Issue**: KeyError when namespace replaced
   - **Mitigation**: Always use update(), never assign
   - **Test**: Verify _ and __ work after execution

2. **Thread Safety Violation**
   - **Issue**: Dict corruption from concurrent access
   - **Mitigation**: RLock on all operations
   - **Test**: Concurrent thread and async execution

3. **Coroutine Leaks**
   - **Issue**: Unawaited coroutines accumulate
   - **Mitigation**: WeakSet tracking with cleanup
   - **Test**: Check coroutine count after execution

## Output Requirements

### 1. Executive Summary
- Never replace namespace dictionary (causes KeyError)
- Always merge updates with thread safety
- Track and cleanup coroutines properly
- Preserve engine internals (_ , __, ___)

### 2. Critical Implementation Rules
- [ ] NEVER use `self._namespace = {}`
- [ ] ALWAYS use `self._namespace.update()`
- [ ] ALWAYS acquire lock before namespace access
- [ ] TRACK all coroutines in WeakSet
- [ ] PRESERVE engine internal variables
- [ ] COPY namespace for thread execution

### 3. Test Cases

```python
async def test_namespace_preservation():
    """Test that engine internals are preserved."""
    manager = AsyncNamespaceManager()
    
    # Execute code that returns value
    manager.update_namespace({'result': 42}, 'async')
    
    # Check internals exist (would KeyError in IPython bug)
    ns = manager.namespace
    assert '_' in ns  # Must exist
    assert '__' in ns  # Must exist

async def test_thread_safety():
    """Test concurrent access safety."""
    manager = AsyncNamespaceManager()
    
    async def async_writer():
        for i in range(100):
            manager.update_namespace({f'async_{i}': i}, 'async')
            await asyncio.sleep(0)
    
    def thread_writer():
        for i in range(100):
            manager.update_namespace({f'thread_{i}': i}, 'thread')
    
    # Run concurrently
    thread = threading.Thread(target=thread_writer)
    thread.start()
    await async_writer()
    thread.join()
    
    # Should have all variables without corruption
    ns = manager.namespace
    assert len([k for k in ns if k.startswith('async_')]) == 100
    assert len([k for k in ns if k.startswith('thread_')]) == 100

async def test_coroutine_cleanup():
    """Test that coroutines don't leak."""
    manager = AsyncNamespaceManager()
    
    # Create coroutines
    async def dummy():
        return 42
    
    for i in range(10):
        coro = dummy()
        manager.update_namespace({f'coro_{i}': coro}, 'async')
    
    # Cleanup
    cleaned = manager.cleanup_coroutines()
    assert cleaned == 10
    assert len(manager._pending_coroutines) == 0
```

## Non-Negotiables (REFINED)

1. **No Namespace Replacement**: Always merge
2. **Thread Safety**: RLock required
3. **Coroutine Tracking**: Prevent leaks
4. **Engine Internals**: Must be preserved

## Success Criteria

- [ ] No KeyError from namespace operations
- [ ] Thread-safe concurrent access
- [ ] No coroutine leaks
- [ ] Engine internals preserved
- [ ] Works across async/sync/thread contexts