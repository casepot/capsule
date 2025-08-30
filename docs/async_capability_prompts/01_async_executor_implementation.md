# Async Executor Implementation Planning Prompt

## Your Mission

You are tasked with implementing an async-first execution model that supports top-level await, handles blocking I/O gracefully, and replaces the current ThreadedExecutor. This executor must intelligently route code to the appropriate execution context while maintaining namespace persistence and supporting all modern async Python patterns.

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. Current State Analysis
- **ThreadedExecutor Location**: `src/subprocess/executor.py`
- **What It Does**: Runs user code in threads to support blocking I/O
- **Limitation**: Cannot handle top-level await or async/await naturally
- **What Works**: Input handling via protocol, namespace persistence

### 2. Target Architecture
- **Primary Execution**: Async context by default
- **Top-Level Await**: Must work naturally like IPython/Jupyter
- **Blocking Fallback**: Thread pool for truly blocking operations
- **Code Analysis**: Smart detection of execution requirements

### 3. Files to Modify/Create
- **REPLACE**: `src/subprocess/executor.py` → `src/subprocess/async_executor.py`
- **CREATE**: `src/subprocess/code_analyzer.py` for execution routing
- **UPDATE**: `src/subprocess/worker.py` to use AsyncExecutor
- **MODIFY**: `src/subprocess/namespace.py` to support async operations

## Planning Methodology

### Phase 1: Analysis (40% effort)
<context_gathering>
Goal: Understand execution patterns and async requirements
Stop when: You know how IPython handles top-level await
Depth: Study ast.parse for async detection, asyncio execution patterns
</context_gathering>

Investigate:
1. How IPython detects and executes top-level await
2. When blocking I/O truly needs thread execution
3. How to preserve namespace across async/sync boundaries
4. Coroutine vs regular function detection patterns

### Phase 2: Solution Design (40% effort)

**Core AsyncExecutor Design:**

```python
# src/subprocess/async_executor.py
import asyncio
import ast
import inspect
import textwrap
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

class AsyncExecutor:
    """Async-first executor with intelligent execution routing."""
    
    def __init__(
        self, 
        namespace_manager: NamespaceManager,
        transport: MessageTransport,
        execution_id: str
    ):
        self.namespace = namespace_manager
        self.transport = transport
        self.execution_id = execution_id
        self.thread_pool = ThreadPoolExecutor(max_workers=1)
        self._pending_futures: Dict[str, asyncio.Future] = {}
    
    async def execute(self, code: str) -> Any:
        """Main execution entry point with smart routing."""
        
        # Analyze code to determine execution strategy
        analysis = self.analyze_code(code)
        
        if analysis.has_top_level_await:
            return await self._execute_async_with_await(code)
        elif analysis.has_async_constructs:
            return await self._execute_async(code)
        elif analysis.needs_blocking_io:
            return await self._execute_in_thread(code)
        else:
            # Simple sync code - execute in async context
            return await self._execute_sync_in_async(code)
    
    def analyze_code(self, code: str) -> CodeAnalysis:
        """Analyze code to determine execution requirements."""
        try:
            # Try standard parse first
            tree = ast.parse(code)
            
            # Check for async constructs
            has_await = False
            has_async = False
            has_blocking_io = False
            
            for node in ast.walk(tree):
                # Top-level await detection
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Await):
                    has_await = True
                
                # Async function/for/with detection
                if isinstance(node, (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith)):
                    has_async = True
                
                # Blocking I/O detection (heuristic)
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        # Known blocking functions
                        if node.func.id in ['input', 'sleep', 'requests']:
                            has_blocking_io = True
                    elif isinstance(node.func, ast.Attribute):
                        # Blocking methods like file.read()
                        if node.func.attr in ['read', 'write', 'connect']:
                            has_blocking_io = True
            
            return CodeAnalysis(
                has_top_level_await=has_await,
                has_async_constructs=has_async,
                needs_blocking_io=has_blocking_io
            )
            
        except SyntaxError as e:
            # Might be top-level await that doesn't parse normally
            if 'await' in str(e) or 'await' in code:
                return CodeAnalysis(has_top_level_await=True)
            raise
    
    async def _execute_async_with_await(self, code: str) -> Any:
        """Execute code with top-level await support."""
        
        # Wrap top-level awaits in async function
        if 'await' in code and 'async def' not in code:
            # Indent and wrap
            indented = textwrap.indent(code, '    ')
            wrapped = f"""
async def __async_exec():
{indented}
    return locals()

__exec_result__ = await __async_exec()
"""
            code = wrapped
        
        # Create async-aware namespace
        local_ns = {}
        global_ns = self.namespace.namespace.copy()
        
        # Compile and execute
        compiled = compile(code, '<async_session>', 'exec')
        
        # Execute in current event loop
        exec(compiled, global_ns, local_ns)
        
        # Check if we have a coroutine to await
        if '__exec_result__' in local_ns:
            if asyncio.iscoroutine(local_ns['__exec_result__']):
                result = await local_ns['__exec_result__']
                # Update namespace with results
                if isinstance(result, dict):
                    self.namespace.namespace.update(result)
                return result
            else:
                return local_ns['__exec_result__']
        
        # Update main namespace with changes
        self.namespace.namespace.update(local_ns)
        
        return None
    
    async def _execute_in_thread(self, code: str) -> Any:
        """Execute blocking code in thread pool."""
        
        def thread_execute():
            """Run in thread context."""
            # Use namespace directly
            local_ns = {}
            global_ns = self.namespace.namespace
            
            # Compile and execute
            compiled = compile(code, '<thread_session>', 'exec')
            exec(compiled, global_ns, local_ns)
            
            # Try to get result
            try:
                tree = ast.parse(code, mode='eval')
                compiled_eval = compile(tree, '<thread_session>', 'eval')
                return eval(compiled_eval, global_ns)
            except:
                return None
        
        # Run in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self.thread_pool,
            thread_execute
        )
        
        return result
```

**Code Analysis Module:**

```python
# src/subprocess/code_analyzer.py
from dataclasses import dataclass
import ast
from typing import Set, List

@dataclass
class CodeAnalysis:
    """Analysis results for code execution routing."""
    has_top_level_await: bool = False
    has_async_constructs: bool = False
    needs_blocking_io: bool = False
    imports_found: List[str] = None
    functions_defined: List[str] = None
    classes_defined: List[str] = None
    
    @property
    def execution_mode(self) -> str:
        """Determine execution mode based on analysis."""
        if self.has_top_level_await:
            return "async_with_await"
        elif self.has_async_constructs:
            return "async"
        elif self.needs_blocking_io:
            return "thread"
        else:
            return "sync_in_async"

class CodeAnalyzer:
    """Analyzes Python code for execution requirements."""
    
    # Known blocking I/O functions/modules
    BLOCKING_FUNCTIONS = {
        'input', 'raw_input', 'sleep', 
        'urlopen', 'urlretrieve',
    }
    
    BLOCKING_MODULES = {
        'requests', 'urllib', 'urllib2', 
        'subprocess', 'os.system',
    }
    
    ASYNC_INDICATORS = {
        'await', 'async', 'asyncio',
        'aiohttp', 'aiofiles',
    }
    
    @classmethod
    def analyze(cls, code: str) -> CodeAnalysis:
        """Perform comprehensive code analysis."""
        # ... implementation ...
```

### Phase 3: Risk Assessment (20% effort)

- **Risk**: Breaking existing sync code
  - Mitigation: Default to sync-in-async for unmarked code
  
- **Risk**: Event loop conflicts
  - Mitigation: Use single event loop per subprocess
  
- **Risk**: Namespace corruption across contexts
  - Mitigation: Careful namespace synchronization

## Output Requirements

Your implementation must include:

### 1. Executive Summary
- How async-first changes execution model
- Benefits of top-level await support
- Migration path from ThreadedExecutor
- Performance implications

### 2. Implementation Files

**File 1: async_executor.py**
- AsyncExecutor class with execute() method
- Code analysis and routing logic
- Support for all execution modes
- Proper error handling

**File 2: code_analyzer.py**
- Comprehensive AST-based analysis
- Heuristics for blocking I/O detection
- Execution mode determination

**File 3: Updated worker.py**
```python
# Key changes in worker.py
class SubprocessWorker:
    async def handle_execute(self, message: ExecuteMessage):
        """Use AsyncExecutor instead of ThreadedExecutor."""
        
        # Create async executor
        executor = AsyncExecutor(
            namespace_manager=self.namespace_manager,
            transport=self._transport,
            execution_id=message.id
        )
        
        # Execute with smart routing
        try:
            result = await executor.execute(message.code)
            
            # Send result
            if result is not None:
                await self._send_result(result)
                
        except Exception as e:
            # Handle transaction rollback if needed
            # ...
```

### 3. Test Cases

```python
async def test_top_level_await():
    """Test that top-level await works."""
    code = """
import asyncio
data = await asyncio.sleep(0.1, result='test_data')
data
"""
    result = await executor.execute(code)
    assert result == 'test_data'

async def test_blocking_io_fallback():
    """Test that blocking I/O uses thread."""
    code = """
# This would block event loop without thread
import time
time.sleep(0.1)  # Real blocking sleep
'completed'
"""
    result = await executor.execute(code)
    assert result == 'completed'

async def test_async_function_definition():
    """Test async function definition and calling."""
    code1 = """
async def fetch_data():
    await asyncio.sleep(0.1)
    return {'data': 'test'}
"""
    await executor.execute(code1)
    
    code2 = """
result = await fetch_data()
result
"""
    result = await executor.execute(code2)
    assert result == {'data': 'test'}
```

## Calibration

<context_gathering>
- Search depth: HIGH (architectural change)
- Maximum tool calls: 30-40
- Early stop: Never (need complete understanding)
</context_gathering>

## Non-Negotiables

1. **Top-level await must work**: Core requirement
2. **No event loop blocking**: Blocking I/O must use threads
3. **Namespace persistence**: Works across all execution modes
4. **Backward compatibility**: Existing sync code continues working

## Success Criteria

Before finalizing:
- [ ] Top-level await executes naturally
- [ ] Blocking I/O doesn't freeze event loop
- [ ] Namespace persists across async/sync boundaries
- [ ] All execution modes tested
- [ ] Performance benchmarked

## Additional Guidance

- Study IPython's InteractiveShell.run_cell_async() method
- Look at how Jupyter handles top-level await
- Consider using ast.PyCF_ALLOW_TOP_LEVEL_AWAIT flag
- Thread pool should be configurable (size, timeout)
- Consider caching code analysis results
- Document which patterns trigger which execution mode