# PyREPL3 Comparative Analysis Report
## Following the PARIS Framework

---

## Phase 1: Problem Archaeology
### What Failed Before and Why

### pyrepl2's Approach: Subprocess Isolation
**Success**: Clean process isolation with persistent namespace
```python
# pyrepl2/runner/interpreter.py:57-65
self.namespace: dict[str, Any] = {
    "__name__": "__main__",
    "__doc__": None,
    ...
}
# Single persistent namespace per subprocess
```
**Key Learning**: Namespace persists because subprocess stays alive

### exec-py's Approach: Thread-Based Execution
**Success**: Input handling via thread synchronization
```python
# exec-py/src/pyrepl/runner_async.py:253
local_ns["input"] = await_input  # Override builtin input
```
**Key Learning**: Override input in namespace, not globally

### PyREPL3's Current Issues
1. **Namespace Persistence Bug**: Each `Session()` creates new subprocess = new namespace
2. **Output Streaming Issues**: Complex async/thread bridging causes reliability problems
3. **Missing Override**: Not setting `input` in namespace like exec-py does

---

## Phase 2: Architecture Recognition
### Existing Infrastructure to Leverage

### Namespace Management Patterns

| Project | Approach | Persistence | Isolation |
|---------|----------|------------|-----------|
| **pyrepl2** | Single subprocess per session | ✅ Excellent | ✅ Process-level |
| **exec-py** | Thread per operation | ✅ Global namespace | ⚠️ Thread-level |
| **PyREPL3** | New subprocess per Session | ❌ Lost on restart | ✅ Process-level |

### Key Architectural Differences

#### pyrepl2: Session-Centric
```python
# Session = Long-lived subprocess
SessionContext(
    subprocess=subprocess,  # Reused for all executions
    namespace=persistent_dict  # Maintained across executions
)
```

#### exec-py: Operation-Centric
```python
# Operation = Thread with namespace copy
Operation(
    ns_snapshot = copy(global_ns),  # Transaction support
    thread = Thread(target=execute),  # Isolated execution
)
```

#### PyREPL3: Hybrid (but broken)
```python
# Session creates subprocess, but tests create new Sessions
Session() → subprocess.create_subprocess_exec() → Fresh namespace
```

### Critical Discovery: Input Handling

**exec-py's Solution (WORKS)**:
```python
# Line 253 in runner_async.py
local_ns["input"] = await_input  # Override in namespace
local_ns["__builtins__"]["input"] = await_input  # Also override builtin
```

**PyREPL3's Attempt (INCOMPLETE)**:
```python
# executor.py:160-161
builtins.input = self.create_protocol_input()  # Global override
self._namespace["input"] = builtins.input  # Set in namespace
# BUT: Not preserving between executions!
```

---

## Phase 3: Risk Illumination
### Failure Modes to Avoid

### Risk 1: Subprocess Lifecycle Mismatch
**Pattern**: Creating new subprocess per test/execution
**Impact**: Namespace lost
**Mitigation**: Keep subprocess alive for session duration

### Risk 2: Thread Safety in Output Capture
**Pattern**: Multiple async contexts writing to shared stream
**Impact**: Output corruption, lost data
**Mitigation**: Use thread-safe queues like exec-py

### Risk 3: Input Override Scope
**Pattern**: Global builtins modification
**Impact**: Affects entire process
**Mitigation**: Namespace-scoped override only

### Risk 4: Complex Async/Thread Bridge
**Pattern**: ThreadedExecutor + async transport
**Impact**: Synchronization issues, deadlocks
**Mitigation**: Simpler unidirectional flow

---

## Phase 4: Implementation Scaffolding
### Solutions Based on Learnings

### Fix 1: Namespace Persistence
**Root Cause**: New subprocess per Session instance
**Solution**: Reuse subprocess across executions
```python
class Session:
    def __init__(self):
        self._subprocess = None  # Lazy init
        self._namespace_initialized = False
    
    async def start(self):
        if not self._subprocess:
            self._subprocess = await self._create_subprocess()
            # Subprocess persists until shutdown()
```

### Fix 2: Input Override Pattern
**Root Cause**: Not following exec-py's namespace override
**Solution**: Copy exec-py's approach exactly
```python
def execute_code(self, code: str):
    # Create protocol input function
    protocol_input = self.create_protocol_input()
    
    # Override in namespace (not globally!)
    self._namespace["input"] = protocol_input
    self._namespace["__builtins__"]["input"] = protocol_input
    
    # Execute with modified namespace
    exec(code, self._namespace, self._namespace)
```

### Fix 3: Output Streaming Simplification
**Root Cause**: Complex async/thread output capture
**Solution**: Use pyrepl2's simpler StringIO approach
```python
# pyrepl2 approach: Capture to buffer, send after execution
stdout_buffer = io.StringIO()
with redirect_stdout(stdout_buffer):
    exec(code, namespace)
result["output"] = stdout_buffer.getvalue()
```

### Fix 4: Transaction Support
**Root Cause**: Not implemented
**Solution**: Copy exec-py's snapshot pattern
```python
# Before execution
ns_snapshot = dict(self._namespace)

try:
    exec(code, self._namespace)
    if policy == "commit_on_success":
        pass  # Keep changes
except:
    if policy == "rollback_on_failure":
        self._namespace = ns_snapshot  # Restore
```

---

## Phase 5: Success Validation
### Measurable Criteria

### Critical Fixes Required

| Fix | Success Criteria | Test |
|-----|-----------------|------|
| **Namespace Persistence** | Variables persist between execute() calls | `x=1` then `print(x)` |
| **Class/Function Persistence** | Definitions available in next execution | Define class, instantiate later |
| **Import Tracking** | Imports remain available | `import math` then `math.pi` |
| **Input Override** | input() uses protocol | `name = input()` works |

### Performance Targets (Already Met)
- ✅ Execution latency: 0.62ms (target: 2ms)
- ✅ Output streaming: 1.12ms (target: 10ms)
- ✅ Pool acquisition: 0.021ms (target: 100ms)

---

## Key Insights Summary

### 1. Namespace Persistence Pattern
**pyrepl2 WORKS** because:
- Subprocess lives for entire session
- Single persistent `self.namespace` dictionary
- Explicit tracking of changes

**PyREPL3 FAILS** because:
- Creates new subprocess on each `Session()`
- Tests create new Sessions between executions
- Namespace reinitialized each time

### 2. Input Handling Pattern
**exec-py WORKS** because:
- Overrides `input` in execution namespace
- Uses threading.Event for sync/async bridge
- Clean separation of concerns

**PyREPL3 PARTIALLY WORKS** because:
- Has the infrastructure (ThreadedExecutor)
- But doesn't preserve override between executions
- Complex async coordination

### 3. Output Streaming Pattern
**pyrepl2**: Simple buffer-and-send
**exec-py**: Thread-safe line-buffered streaming
**PyREPL3**: Over-engineered async capture with issues

### 4. Transaction Support
**exec-py**: Full implementation with namespace snapshots
**pyrepl2**: No transactions (not needed)
**PyREPL3**: Messages defined but not implemented

---

## Recommended Actions

### Immediate (Fix Blocking Issues)
1. **Fix Session lifecycle**: Don't create new subprocess per Session
2. **Fix namespace persistence**: Keep subprocess alive
3. **Simplify output capture**: Use StringIO approach

### Short Term (Complete Features)
1. **Implement transactions**: Copy exec-py's snapshot pattern
2. **Fix input override**: Follow exec-py's namespace approach
3. **Add checkpoint/restore**: Use pyrepl2's serialization

### Long Term (Architecture)
1. **Choose philosophy**: Session-centric (pyrepl2) or Operation-centric (exec-py)
2. **Simplify threading model**: Reduce async/thread complexity
3. **Standardize on patterns**: Pick best from each predecessor

---

## Conclusion

PyREPL3 has taken good ideas from both predecessors but hasn't fully implemented them:
- Has pyrepl2's subprocess isolation ✅
- Has exec-py's threaded execution ✅
- Missing pyrepl2's persistent subprocess ❌
- Missing exec-py's namespace input override ❌
- Over-complicated the output streaming ❌

The fixes are straightforward:
1. Keep subprocess alive (like pyrepl2)
2. Override input in namespace (like exec-py)
3. Simplify output capture (like pyrepl2)
4. Implement transactions (like exec-py)

With these changes, PyREPL3 would combine the best of both architectures.