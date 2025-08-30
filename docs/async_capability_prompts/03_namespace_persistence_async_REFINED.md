# Namespace Persistence Across Async/Sync Boundaries Planning Prompt (REFINED with Resonate)

## Your Mission

You are tasked with ensuring namespace persistence works correctly across async and sync execution contexts using Resonate's durable state management. Based on investigation, the critical insight remains: **NEVER replace the namespace dictionary entirely** - this causes KeyError failures. Always merge updates while preserving execution engine internals. Resonate now provides durability for the namespace across crashes and restarts.

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

**Durable Namespace Manager with Resonate:**

```python
# src/subprocess/namespace.py - RESONATE ENHANCED
import json
import threading
from typing import Any, Dict, Set, Optional
from resonate_sdk import Resonate

class DurableNamespaceManager:
    """Namespace manager with Resonate durability and critical safety improvements."""
    
    def __init__(self, resonate: Resonate, execution_id: str):
        self.resonate = resonate
        self.execution_id = execution_id
        
        # CRITICAL: Thread-safe access still needed for local operations
        self._namespace_lock = threading.RLock()
        
        # The actual namespace - can be recovered from Resonate
        self._namespace = self._initialize_or_recover_namespace()
        
        # CRITICAL: Preserve engine internals
        self._preserved_keys: Set[str] = set()
        self._init_engine_internals()
    
    def _initialize_or_recover_namespace(self) -> Dict[str, Any]:
        """Initialize or recover namespace from Resonate."""
        namespace_id = f"namespace:{self.execution_id}"
        
        try:
            # Try to recover existing namespace
            promise = self.resonate.promises.get(namespace_id)
            if promise and promise.state == 'resolved':
                return json.loads(promise.data)
        except:
            pass
        
        # Initialize fresh namespace
        return {
            "__name__": "__main__",
            "__doc__": None,
            "__package__": None,
            "__loader__": None,
            "__spec__": None,
            "__annotations__": {},
            "__builtins__": __builtins__,
        }
    
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
    
    def persist_namespace(self):
        """Persist namespace to Resonate for durability."""
        namespace_id = f"namespace:{self.execution_id}"
        
        # Serialize namespace (skip non-serializable items)
        serializable_ns = {}
        for key, value in self._namespace.items():
            try:
                json.dumps(value)  # Test if serializable
                serializable_ns[key] = value
            except:
                # Skip functions, modules, etc.
                pass
        
        # Create or update promise with namespace state
        self.resonate.promises.resolve(
            id=namespace_id,
            data=json.dumps(serializable_ns)
        )
    
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
                
                # With Resonate, coroutines are handled differently
                # Resonate uses generators with yield, not asyncio coroutines
                if hasattr(value, '__name__') and 'resonate' in str(type(value)):
                    # This is a Resonate durable function
                    filtered_updates[key] = value
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

**Execution with Resonate Durable Functions:**

```python
# src/subprocess/durable_execution.py
from resonate_sdk import Resonate

@resonate.register
def durable_execute_with_namespace(ctx, args):
    """Execute code with durable namespace management."""
    code = args['code']
    execution_id = args['execution_id']
    
    # Get namespace manager from dependencies
    namespace_manager = ctx.get_dependency("namespace_manager")
    
    # Initialize or recover namespace for this execution
    namespace = namespace_manager.get_for_execution(execution_id)
    
    # Local namespace for this execution
    local_ns = {}
    
    try:
        # Compile and execute
        compiled = compile(code, f'<execution:{execution_id}>', 'exec')
        exec(compiled, namespace, local_ns)
        
        # CRITICAL: Merge updates, never replace
        namespace_manager.update_namespace(local_ns, 'durable')
        
        # Persist namespace state to Resonate
        yield ctx.lfc(namespace_manager.persist_namespace)
        
        # Check for result
        result = local_ns.get('_result') or namespace.get('_')
        
        return result
        
    except Exception as e:
        # Store exception in namespace
        namespace_manager.update_namespace(
            {'_exception': e},
            source_context='engine'
        )
        # Persist error state
        yield ctx.lfc(namespace_manager.persist_namespace)
        raise
    
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
- Never replace namespace dictionary (causes KeyError) - **Critical lesson preserved**
- Always merge updates with thread safety - **Still required**
- Resonate provides durability and crash recovery - **NEW capability**
- Namespace as durable state across executions - **NEW with Resonate**
- Preserve engine internals (_, __, ___) - **Always critical**

### Benefits of Resonate Integration:
1. **Crash Recovery**: Namespace survives process crashes
2. **Distributed State**: Share namespace across workers
3. **Simplified Coroutines**: No async/await complexity with yield
4. **Automatic Persistence**: Built into execution lifecycle
5. **Time Travel**: Can recover namespace from any point

### 2. Critical Implementation Rules
- [ ] NEVER use `self._namespace = {}`
- [ ] ALWAYS use `self._namespace.update()`
- [ ] ALWAYS acquire lock before namespace access
- [ ] TRACK all coroutines in WeakSet
- [ ] PRESERVE engine internal variables
- [ ] COPY namespace for thread execution

### 3. Test Cases

```python
def test_namespace_preservation():
    """Test that engine internals are preserved."""
    resonate = Resonate.local()
    manager = DurableNamespaceManager(resonate, 'test-1')
    
    # Execute code that returns value
    manager.update_namespace({'result': 42}, 'durable')
    
    # Check internals exist (would KeyError in IPython bug)
    ns = manager.namespace
    assert '_' in ns  # Must exist
    assert '__' in ns  # Must exist

def test_namespace_recovery():
    """Test namespace recovery after crash."""
    resonate = Resonate.remote()  # Requires server
    
    # First execution creates namespace
    result1 = durable_execute_with_namespace.run("exec-1", {
        'code': 'x = 42',
        'execution_id': 'exec-1'
    })
    
    # Simulate crash and recovery
    # Namespace should be recovered from Resonate
    result2 = durable_execute_with_namespace.run("exec-1", {
        'code': 'result = x * 2',  # Uses x from recovered namespace
        'execution_id': 'exec-1'
    })
    
    assert result2 == 84  # Proves namespace was recovered

def test_namespace_durability():
    """Test namespace persists across executions."""
    resonate = Resonate.local()
    resonate.set_dependency("namespace_manager", DurableNamespaceManager)
    
    # Register durable function
    @resonate.register
    def test_execution(ctx, args):
        nm = ctx.get_dependency("namespace_manager")
        namespace = nm.get_for_execution(args['exec_id'])
        
        # Execute code
        exec(args['code'], namespace)
        
        # Update and persist
        nm.update_namespace(namespace, 'durable')
        yield ctx.lfc(nm.persist_namespace)
        
        return namespace.get('result')
    
    # Multiple executions share namespace
    test_execution.run("test-1", {'exec_id': 'shared', 'code': 'a = 1'})
    test_execution.run("test-2", {'exec_id': 'shared', 'code': 'b = 2'})
    result = test_execution.run("test-3", {'exec_id': 'shared', 'code': 'result = a + b'})
    
    assert result == 3  # Namespace persisted across executions
```

## Non-Negotiables (REFINED with Resonate)

1. **No Namespace Replacement**: Always merge (critical lesson preserved)
2. **Thread Safety**: RLock still required for local operations
3. **Resonate Integration**: Namespace as durable dependency
4. **Engine Internals**: Must be preserved (_, __, ___)
5. **Persistence Strategy**: Serialize only JSON-compatible values

## Success Criteria (Enhanced with Resonate)

- [ ] No KeyError from namespace operations (preserved lesson)
- [ ] Thread-safe concurrent access (still required)
- [ ] Namespace survives process crashes (NEW with Resonate)
- [ ] Engine internals preserved (_, __, ___)
- [ ] Works across async/sync/thread contexts
- [ ] Namespace state recoverable from Resonate promises
- [ ] Automatic persistence on execution boundaries
- [ ] Shared namespace across distributed workers (remote mode)