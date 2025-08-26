# Execution and Output Handling (Including Turn-by-Turn Execution)

## Overview

The implementations differ significantly in execution architecture:

- **exec-py**: Thread-based execution with real-time event streaming
- **pyrepl2**: Subprocess-based execution with structured result batching

## exec-py/src/pyrepl Implementation

### Thread-Based Execution Model

exec-py spawns a thread per operation (`runner_async.py:232-285`):

```python
def _worker_body() -> None:
    op.state = "RUNNING"
    
    # stdout/err redirection
    def emit_stdout(s: str) -> None:
        emit.emit({"kind": "OUTPUT", "stream": "stdout", "data": s})  
    
    def emit_stderr(s: str) -> None:
        emit.emit({"kind": "OUTPUT", "stream": "stderr", "data": s})
    
    stdout = _StdStream(emit_stdout)
    stderr = _StdStream(emit_stderr)
    
    try:
        with (
            contextlib.redirect_stdout(cast("IO[str]", stdout)),
            contextlib.redirect_stderr(cast("IO[str]", stderr)),
        ):
            # Install helpers
            local_ns = op.ns
            local_ns["await_input"] = await_input
            local_ns["input"] = await_input  # v0.1.1: Override builtin input
            # Execute code
            exec(compile(code, "<exec>", "exec"), local_ns, local_ns)
            result_obj = local_ns.get("_")  # conventional last expression, if set
```

### Real-Time Event Streaming

exec-py implements streaming output with custom streams (`runner_async.py:69-88`):

```python
class _StdStream(io.TextIOBase):
    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._buffer = ""
    
    def write(self, s: str) -> int:
        if not isinstance(s, str):
            s = str(s)
        # Buffer until newline or flush to avoid tiny chunks
        self._buffer += s
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit(line + "\n")
        return len(s)
```

### Turn-by-Turn Execution

exec-py handles streaming execution via events (`manager.py:256-274`):

```python
def exec_stream(self, code: str, *, timeout_s: float = 60.0) -> AsyncGenerator[dict[str, Any], None]:
    async def _gen() -> AsyncGenerator[dict[str, Any], None]:
        start = await self._send("exec_stream", {"code": code})
        op_id = start.payload["op_id"]
        q = self._events.setdefault(op_id, asyncio.Queue(self._max_q))
        # emit OP_STARTED synthetic event with op_id
        yield {"kind": "OP_STARTED", "op_id": op_id}
        # drain events until terminal
        try:
            while True:
                ev = await asyncio.wait_for(q.get(), timeout=timeout_s)
                ev["op_id"] = op_id
                yield ev
                if ev.get("kind") in ("OP_COMPLETED", "RESULT", "OP_FAILED", "OP_CANCELLED"):
                    break
        finally:
            self._events.pop(op_id, None)
    
    return _gen()
```

### Event Types

exec-py defines various event types for streaming (`protocol.py:148-186`):

```python
class OutputEvent(TypedDict):
    kind: str
    stream: str
    data: str

class InputRequestEvent(TypedDict):
    kind: str
    token: str
    prompt: str

class ResultEvent(TypedDict):
    kind: str
    ok: bool
    result: Any
```

### Input Handling

Interactive input during execution (`runner_async.py:221-230`):

```python
def await_input(prompt: str = "input: ") -> str:
    token = uuid.uuid4().hex
    evt = threading.Event()
    op.input_waiters[token] = InputWaiter(token, evt)
    emit.emit({"kind": "INPUT_REQUEST", "token": token, "prompt": prompt})
    evt.wait()
    w = op.input_waiters.pop(token, None)
    if op.cancelled:
        raise RuntimeError("Operation cancelled while waiting for input")
    return w.value if w and w.value is not None else ""
```

## pyrepl2/pyrepl2 Implementation

### Subprocess-Based Execution

pyrepl2 executes code in an isolated subprocess (`runner/interpreter.py:151-268`):

```python
def execute(self, code: str, timeout: float = 30.0) -> dict[str, Any]:
    """Execute code in persistent namespace."""
    start_time = time.time()
    
    # Reset interrupt flag
    self._interrupted = False
    
    # Capture output
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    
    result = {
        "status": "success",
        "output": "",
        "error": None,
        "traceback": None,
        "execution_time_ms": 0.0,
        "memory_delta_mb": 0.0,
        "namespace_changes": {},
        "return_value": None,
    }
```

### Output Capture Strategy

pyrepl2 captures output in buffers (`runner/interpreter.py:198-232`):

```python
# Execute with output capture
with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
    # Check if last statement is an expression
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        # Split into statements and final expression
        if len(tree.body) > 1:
            # Execute all statements except the last
            exec_tree = ast.Module(body=tree.body[:-1], type_ignores=[])
            exec(compile(exec_tree, "<session>", "exec"), self.namespace)
        
        # Evaluate the last expression for return value
        expr_tree = ast.Expression(body=tree.body[-1].value)
        result["return_value"] = eval(
            compile(expr_tree, "<session>", "eval"), self.namespace
        )
    else:
        # No expression at end, execute everything normally
        exec(compile(tree, "<session>", "exec"), self.namespace)

result["output"] = stdout_buffer.getvalue()
```

### Expression Evaluation

pyrepl2 intelligently handles return values (`runner/interpreter.py:200-222`):

```python
# Parse the code to properly handle return values
tree = ast.parse(code)

# Check if last statement is an expression
if tree.body and isinstance(tree.body[-1], ast.Expr):
    # Split into statements and final expression
    if len(tree.body) > 1:
        # Execute all statements except the last
        exec_tree = ast.Module(body=tree.body[:-1], type_ignores=[])
        exec(compile(exec_tree, "<session>", "exec"), self.namespace)
    
    # Evaluate the last expression for return value
    expr_tree = ast.Expression(body=tree.body[-1].value)
    result["return_value"] = eval(
        compile(expr_tree, "<session>", "eval"), self.namespace
    )
```

### Structured Results

pyrepl2 returns comprehensive execution results (`types/execution.py:66-83`):

```python
@dataclass(slots=True)
class ExecutionResult:
    """Result from code execution."""
    
    status: ExecutionStatus
    output: str = ""
    error: str | None = None
    traceback: str | None = None
    execution_time_ms: float = 0.0
    memory_delta_mb: float = 0.0
    namespace_changes: dict[str, NamespaceChange] = field(default_factory=dict)
    return_value: Any | None = None
    
    @property
    def success(self) -> bool:
        """Check if execution succeeded."""
        return self.status == ExecutionStatus.SUCCESS
```

### No Native Turn-by-Turn

pyrepl2 doesn't provide native streaming - results are returned as a batch after execution completes. However, turn-by-turn could be implemented at a higher level by executing code blocks sequentially.

## Comparison Table

| Feature | exec-py | pyrepl2 |
|---------|---------|---------|
| **Execution Model** | Thread per operation | Subprocess per session |
| **Output Strategy** | Real-time streaming | Buffered capture |
| **Event Types** | Multiple (OUTPUT, INPUT_REQUEST, RESULT, etc.) | Single result object |
| **Return Values** | Convention-based (`_` variable) | AST-based expression evaluation |
| **Input Handling** | Async with tokens | Not implemented in base |
| **Error Handling** | Event-based | Structured in result |
| **Memory Tracking** | Not implemented | Delta measurement |
| **Namespace Changes** | Not tracked | Detailed change detection |
| **Turn-by-Turn** | Native streaming support | Sequential execution possible |

## Output Handling Examples

### Simple Print Statement

**exec-py:**
```python
# Client receives events:
{"kind": "OP_STARTED", "op_id": "abc123"}
{"kind": "OUTPUT", "stream": "stdout", "data": "Hello, World!\n"}
{"kind": "RESULT", "ok": true, "result": null}
```

**pyrepl2:**
```python
# Client receives single result:
{
    "status": "success",
    "output": "Hello, World!\n",
    "error": None,
    "execution_time_ms": 0.5,
    "return_value": None
}
```

### Interactive Input

**exec-py:**
```python
# Code: name = await_input("Enter name: ")
# Events:
{"kind": "INPUT_REQUEST", "token": "xyz789", "prompt": "Enter name: "}
# Client sends: {"kind": "input_response", "token": "xyz789", "data": "Alice"}
{"kind": "OUTPUT", "stream": "stdout", "data": "Hello, Alice!\n"}
```

**pyrepl2:**
```python
# Input not supported in base implementation
# Would require custom capability injection
```

## Turn-by-Turn Execution Patterns

### exec-py Streaming Pattern
```python
async for event in client.exec_stream("""
print("Step 1")
time.sleep(1)
print("Step 2")
result = 42
"""):
    if event["kind"] == "OUTPUT":
        print(f"Output: {event['data']}")
    # Outputs appear as they happen
```

### pyrepl2 Sequential Pattern
```python
# Execute in chunks for turn-by-turn behavior
chunks = ["print('Step 1')", "time.sleep(1)", "print('Step 2')", "result = 42"]
for chunk in chunks:
    result = await protocol.execute(session_id, chunk)
    if result.output:
        print(f"Output: {result.output}")
    # Each chunk completes before next starts
```

## Tradeoff Analysis

### exec-py Execution

**Advantages:**
- Real-time output streaming
- Interactive input support
- Fine-grained event tracking
- Lower latency for output
- Natural turn-by-turn execution

**Disadvantages:**
- Thread safety complexity
- No process isolation
- Limited parallelism (GIL)
- No memory tracking

### pyrepl2 Execution

**Advantages:**
- Process isolation
- Memory delta tracking
- Namespace change detection
- Clean error boundaries
- Return value extraction

**Disadvantages:**
- No real-time streaming
- Batched output only
- Higher latency
- No built-in input support

## Key Design Philosophy

The execution models reflect different priorities:

- **exec-py**: Optimized for **interactive, streaming execution** with real-time feedback
- **pyrepl2**: Optimized for **batch execution with comprehensive results**

exec-py treats execution as an ongoing conversation with events flowing between client and runner, while pyrepl2 treats it as discrete transactions with structured responses. This makes exec-py better for interactive REPLs and pyrepl2 better for notebook-style execution cells.