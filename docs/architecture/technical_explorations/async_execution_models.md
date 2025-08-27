# Async Execution Models

## Current State: Thread-Based Execution

The current implementation runs all user code in threads:

- `src/subprocess/worker.py:347-355` - Thread creation
- `src/subprocess/executor.py:149-199` - Code execution in thread

### What This Enables
- Blocking I/O (input(), time.sleep())
- Standard Python semantics
- No special async handling

### What This Prevents
- Top-level await
- Direct event loop access
- Native async performance

## Async Code Support Investigation

Currently, users must wrap async code:

```python
# Works:
async def foo(): ...
result = asyncio.run(foo())

# Doesn't work (SyntaxError):
await foo()
```

### AST Analysis Approach

Consider detecting async constructs:

```python
# Potential investigation in worker.py
tree = ast.parse(code)
has_await = any(isinstance(node, (ast.Await, ast.AsyncFor, ast.AsyncWith))
                for node in ast.walk(tree))
```

## Execution Strategy Decision Points

### Option 1: Always Thread
- Simple, consistent
- No async detection needed
- But no top-level await

### Option 2: Detect and Route
- Sync → thread
- Async → event loop
- Complex detection logic

### Option 3: Always Async
- Wrap sync code in async
- Native async support
- But overhead for simple code

## IPython Comparison

IPython uses AST transformation (see their `async_helpers.py`):
1. Try compile normally
2. If SyntaxError with await, wrap in async def
3. Run wrapped function

### Questions This Raises

- Is heuristic detection reliable?
- Should error messages guide users?
- How to handle partial async support?

## Implementation Exploration Areas

1. **Where to detect**: In worker before execution? In executor?
2. **How to execute**: Reuse worker loop? Create new? Thread event loop?
3. **Namespace compatibility**: Do async and sync executions share namespace correctly?

Look at:
- How `compile()` handles async code
- Whether exec() supports top-level await in any mode
- Python 3.11+ async REPL implementation

## Performance Implications

Consider benchmarking:
- Thread creation overhead
- Event loop task overhead  
- Context switching costs
- Memory usage patterns