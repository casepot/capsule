# Async Executor Implementation Planning Prompt (REFINED with Resonate)

## Your Mission

You are tasked with implementing an async-first execution model that supports top-level await WITHOUT using IPython as a dependency. Build a custom async executor using the compile flag `PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x1000000` discovered through investigation, wrapped in Resonate durable functions for automatic recovery and distributed execution support.

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. Problem History (NEW INSIGHT)
- **IPython Integration Attempt**: Failed due to `_oh` KeyError when replacing namespace
- **Key Lesson**: Never replace user_ns entirely - must preserve execution engine internals
- **Invariant**: Namespace must be under our control without breaking display hooks

### 2. Critical Technical Discovery
- **The Magic Flag**: `PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x1000000` enables top-level await in compile()
- **How It Works**: Add to compile flags: `compile(code, '<session>', 'exec', flags=base_flags | 0x1000000)`
- **Edge Case**: Some code needs AST transformation before compilation

### 3. Architecture Recognition
- **ThreadedExecutor**: Works perfectly for sync/blocking code - DO NOT break it
- **Protocol Transport**: Already async-aware but needs careful event loop management
- **Namespace Manager**: Thread-safe but needs async context awareness

### 4. Constraints That Cannot Be Violated
- **No IPython Dependency**: We build our own to maintain control
- **Cancellation Support**: Must support sys.settrace for sync, but async is harder
- **Protocol Order**: Message ordering must be preserved despite async execution
- **Memory Safety**: No coroutine leaks in namespace

## Planning Methodology

### Phase 1: Analysis (30% effort - REDUCED from 40%)
<context_gathering>
Goal: Extract IPython's top-level await patterns WITHOUT inheriting its problems
Stop when: You understand compile flag usage and AST transformation needs
Depth: Focus on compile() mechanics, NOT IPython internals
</context_gathering>

Key Investigation Points:
1. How to detect if code needs `PyCF_ALLOW_TOP_LEVEL_AWAIT`
2. When AST transformation is required vs direct compilation  
3. How to handle coroutine results vs regular returns
4. Event loop lifecycle in subprocess context

### Phase 2: Solution Design (50% effort - INCREASED focus on implementation)

**Core AsyncExecutor Design (REFINED with Resonate):**

```python
# src/subprocess/async_executor.py
import ast
import asyncio
import sys
import types
from typing import Any, Dict, Optional
from resonate_sdk import Resonate

class AsyncExecutor:
    """Custom async executor with top-level await support and Resonate durability."""
    
    # Critical discovery from investigation
    PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x1000000
    
    def __init__(
        self, 
        resonate: Resonate,
        namespace_manager: NamespaceManager,
        execution_id: str
    ):
        self.resonate = resonate
        self.namespace = namespace_manager
        self.execution_id = execution_id
        # DO NOT create new event loop - use existing
        self.loop = asyncio.get_event_loop()
        
    async def execute(self, code: str) -> Any:
        """Execute with top-level await support."""
        
        # Detect execution mode
        mode = self._analyze_execution_mode(code)
        
        if mode == 'top_level_await':
            return await self._execute_with_top_level_await(code)
        elif mode == 'async_def':
            return await self._execute_async_definitions(code)
        elif mode == 'blocking_sync':
            # Delegate to ThreadedExecutor for blocking I/O
            return await self._execute_in_thread(code)
        else:
            # Simple sync code
            return self._execute_sync(code)
    
    def _analyze_execution_mode(self, code: str) -> str:
        """Determine execution mode - REFINED logic."""
        try:
            # Try to parse normally first
            tree = ast.parse(code)
            
            # Check for await at module level (not inside function)
            for node in tree.body:
                if isinstance(node, ast.Expr):
                    if self._contains_await(node.value):
                        return 'top_level_await'
            
            # Check for async function definitions
            if any(isinstance(n, ast.AsyncFunctionDef) for n in ast.walk(tree)):
                return 'async_def'
            
            # Check for blocking I/O patterns
            if self._contains_blocking_io(tree):
                return 'blocking_sync'
            
            return 'simple_sync'
            
        except SyntaxError as e:
            # Likely has top-level await that doesn't parse
            if 'await' in str(e) or 'await' in code:
                return 'top_level_await'
            raise
    
    def _contains_await(self, node: ast.AST) -> bool:
        """Check if node contains await expression."""
        if isinstance(node, ast.Await):
            return True
        for child in ast.walk(node):
            if isinstance(child, ast.Await):
                return True
        return False
    
    async def _execute_with_top_level_await(self, code: str) -> Any:
        """Execute code with top-level await - NEW IMPLEMENTATION."""
        
        # Get base compile flags
        base_flags = compile('', '', 'exec').co_flags
        
        # Add the magic flag for top-level await
        flags = base_flags | self.PyCF_ALLOW_TOP_LEVEL_AWAIT
        
        try:
            # Try direct compilation with the flag
            compiled = compile(code, '<async_session>', 'exec', flags=flags)
            
            # Create namespace (DO NOT replace, merge!)
            local_ns = {}
            global_ns = self.namespace.namespace.copy()
            
            # Execute - may return a coroutine
            result = eval(compiled, global_ns, local_ns)
            
            # Handle coroutine result
            if asyncio.iscoroutine(result):
                result = await result
            
            # Update namespace with changes (merge, don't replace!)
            self.namespace.update_namespace(local_ns, source_context='async')
            
            return result
            
        except SyntaxError:
            # Needs AST transformation - wrap in async function
            return await self._execute_with_ast_transform(code)
    
    async def _execute_with_ast_transform(self, code: str) -> Any:
        """Transform code for top-level await - FALLBACK."""
        
        # Parse and modify AST
        tree = ast.parse(code)
        
        # Wrap in async function
        async_wrapper = ast.AsyncFunctionDef(
            name='__async_exec__',
            args=ast.arguments(
                posonlyargs=[], args=[], kwonlyargs=[], 
                kw_defaults=[], defaults=[]
            ),
            body=tree.body,
            decorator_list=[],
            returns=None
        )
        
        # Create module with wrapper
        new_tree = ast.Module(body=[async_wrapper], type_ignores=[])
        ast.fix_missing_locations(new_tree)
        
        # Compile and execute
        compiled = compile(new_tree, '<async_transform>', 'exec')
        
        local_ns = {}
        global_ns = self.namespace.namespace.copy()
        
        exec(compiled, global_ns, local_ns)
        
        # Get the async function and execute it
        async_func = local_ns['__async_exec__']
        result = await async_func()
        
        return result

# Resonate Durable Wrapper

@resonate.register
def durable_execute(ctx, args):
    """Durable execution with automatic recovery."""
    code = args['code']
    execution_id = args['execution_id']
    namespace = args.get('namespace', {})
    
    # Get dependencies from Resonate context
    namespace_manager = ctx.get_dependency("namespace_manager")
    
    # Create executor instance
    executor = AsyncExecutor(
        resonate=ctx.resonate,
        namespace_manager=namespace_manager,
        execution_id=execution_id
    )
    
    # Analyze code to determine execution mode
    analysis = analyze_code(code)
    
    if analysis.has_top_level_await:
        # Execute with top-level await support
        result = yield ctx.lfc(execute_async_with_await, {
            'executor': executor,
            'code': code,
            'flags': AsyncExecutor.PyCF_ALLOW_TOP_LEVEL_AWAIT
        })
    elif analysis.needs_blocking_io:
        # Use thread pool for blocking I/O
        result = yield ctx.lfc(execute_in_thread, {
            'code': code,
            'namespace': namespace
        })
    else:
        # Simple sync execution
        result = executor._execute_sync(code)
    
    return result

# Initialize Resonate for local development (no server required)
def initialize_executor_system():
    """Initialize with Resonate in local or remote mode."""
    import os
    
    if os.getenv('RESONATE_REMOTE'):
        # Production mode with crash recovery
        resonate = Resonate.remote(host=os.getenv('RESONATE_HOST', 'http://localhost:8001'))
    else:
        # Local development - no external dependencies
        resonate = Resonate.local()
    
    # Register durable functions
    resonate.register(durable_execute)
    resonate.register(execute_async_with_await)
    resonate.register(execute_in_thread)
    
    # Set up dependencies
    resonate.set_dependency("namespace_manager", NamespaceManager())
    
    return resonate
```

### Phase 3: Risk Mitigation (20% effort - FOCUSED on discovered issues)

**Critical Risks from Investigation:**

1. **Namespace Corruption Risk**
   - **Issue**: IPython's `_oh` KeyError when replacing namespace
   - **Mitigation**: ALWAYS merge namespace updates, never replace
   - **Implementation**: Use `namespace.update()` not `namespace = {}`

2. **Event Loop Conflicts**  
   - **Issue**: Protocol messages need async context
   - **Mitigation**: Queue messages when not in async context
   - **Implementation**: Message buffer with `await send_pending()`

3. **Coroutine Leaks**
   - **Issue**: Unawaited coroutines left in namespace
   - **Mitigation**: Track and cleanup coroutines
   - **Implementation**: `_pending_coroutines` registry with cleanup

4. **Cancellation Complexity**
   - **Issue**: sys.settrace doesn't work for async code
   - **Mitigation**: Use asyncio.Task cancellation
   - **Implementation**: Track running tasks and cancel on interrupt

## Output Requirements

### 1. Executive Summary
- Build custom async executor using `PyCF_ALLOW_TOP_LEVEL_AWAIT` flag
- Avoid IPython's namespace coupling issues entirely
- Preserve ThreadedExecutor for blocking I/O
- Maintain protocol message ordering through careful async management
- Zero dependencies beyond standard library

### 2. Implementation Checklist
- [ ] Use `PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x1000000` flag
- [ ] Never replace namespace entirely (merge only)
- [ ] Handle both compilable and AST-transform cases
- [ ] Track pending coroutines for cleanup
- [ ] Preserve ThreadedExecutor for blocking I/O
- [ ] Queue protocol messages when not in async context

### 3. Test Cases (CRITICAL)

```python
async def test_compile_flag_usage():
    """Verify the magic flag enables top-level await."""
    code = "import asyncio; result = await asyncio.sleep(0, 'test')"
    
    # This MUST work with our flag
    flags = compile('', '', 'exec').co_flags | 0x1000000
    compiled = compile(code, '<test>', 'exec', flags=flags)
    assert compiled is not None

async def test_namespace_preservation():
    """Ensure namespace updates don't cause KeyError."""
    resonate = Resonate.local()
    namespace_manager = NamespaceManager()
    executor = AsyncExecutor(resonate, namespace_manager, 'test-id')
    
    # Execute code that returns a value
    await executor.execute("result = 42")
    
    # This must NOT raise KeyError like IPython did
    await executor.execute("result")  # Display hook equivalent
    
async def test_no_coroutine_leak():
    """Verify coroutines are properly managed."""
    initial_tasks = len(asyncio.all_tasks())
    
    await executor.execute("import asyncio; await asyncio.sleep(0)")
    
    # No leaked tasks
    assert len(asyncio.all_tasks()) == initial_tasks

def test_resonate_local_mode():
    """Test execution works without server."""
    resonate = Resonate.local()
    
    result = durable_execute.run("test-1", {
        'code': "result = 2 + 2",
        'execution_id': "test-1"
    })
    assert result == 4

def test_resonate_recovery():
    """Test execution recovers from crash."""
    resonate = Resonate.remote()  # Requires server
    
    # Start execution that will crash
    promise = durable_execute.rpc("test-2", {
        'code': "import random; x = 1/random.choice([0, 1])",
        'execution_id': "test-2"
    })
    
    # Retry will resume from checkpoint
    result = durable_execute.run("test-2", {'code': "x = 1", 'execution_id': "test-2"})
    assert result == 1
```

## Calibration

<context_gathering>
- Search depth: LOW (we know the solution from investigation)
- Maximum tool calls: 10-15 (verification only)
- Early stop: When compile flag works with test code
</context_gathering>

## Non-Negotiables (REFINED)

1. **No IPython Dependency**: Build our own implementation
2. **Use PyCF_ALLOW_TOP_LEVEL_AWAIT**: This is THE key to top-level await
3. **Preserve Namespace Control**: No `_oh` or IPython internals
4. **Maintain ThreadedExecutor**: It works well for blocking I/O

## Success Criteria (REFINED with Resonate)

- [ ] Top-level await works with `PyCF_ALLOW_TOP_LEVEL_AWAIT` flag
- [ ] No namespace KeyErrors (avoided IPython's pitfall)
- [ ] Protocol messages maintain order via Resonate promises
- [ ] Blocking I/O still uses threads
- [ ] Zero external dependencies in local mode (Resonate.local())
- [ ] Automatic recovery in remote mode (Resonate.remote())
- [ ] Execution state persists across crashes
- [ ] Dependencies injected via Resonate context

## Critical Implementation Note

**DO NOT** attempt to replicate IPython's InteractiveShell complexity. We need ONLY:
1. The compile flag for top-level await
2. AST transformation for edge cases  
3. Careful namespace merging (not replacement)
4. Protocol message queuing

This is ~400 lines of code, not 2000 like IPython.