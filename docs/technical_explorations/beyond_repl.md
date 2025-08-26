# Beyond REPL: Execution Service Patterns

## REPL Limitations

Traditional REPL assumes:
- **R**ead: Text from stdin
- **E**val: One expression
- **P**rint: Text to stdout  
- **L**oop: Sequential, blocking

## Current PyREPL3 Patterns

Examine how PyREPL3 already transcends REPL:

- **Read**: Protocol messages, not stdin (`src/protocol/messages.py`)
- **Eval**: Stateful execution in subprocess (`src/subprocess/worker.py`) 
- **Print**: Structured output messages (`OutputMessage`, `ResultMessage`)
- **Loop**: Concurrent message handling (`asyncio.create_task`)

## Session-Oriented RPC vs Traditional Patterns

### Traditional RPC
```python
# Stateless - each call independent
result = rpc.call("add", 2, 3)
```

### PyREPL3's Session-Oriented RPC
```python
# Stateful - maintains context
session.execute("x = 5")
session.execute("y = x * 2")  # Can reference x
```

### Investigation Points

- Where is session state maintained? (`_namespace` in worker.py)
- How does session affinity work in the pool?
- What breaks if we make it stateless?

## Alternative Execution Models to Explore

### Notebook Model
- Non-linear execution
- Cell dependencies
- Output caching

Questions:
- Could execution messages have dependency graphs?
- How would output be associated with cells?

### Pipeline Model  
- DAG of computations
- Parallel execution
- Result caching

Consider:
- Could ExecuteMessage have upstream dependencies?
- How would the worker handle parallel execution?

### Workspace Model
- Multiple concurrent executions
- Shared state with isolation
- Tool integration

Investigate:
- Could one worker handle multiple threads?
- How would namespace isolation work?

## Technical Positioning Analysis

PyREPL3 sits between:

| Lighter Than | PyREPL3 | Heavier Than |
|--------------|---------|--------------|
| Thread pools | Process isolation | Docker containers |
| Async executors | Persistent state | Kubernetes pods |
| eval() | Resource limits | VMs |

### Questions This Raises

1. Is process-per-session the right granularity?
2. Could we support both thread and process isolation?
3. What would container-based isolation add?

## Service Patterns to Consider

### Current: One Process Per Session
- Simple isolation
- Clear resource boundaries
- But scaling limitations?

### Alternative: Worker Pool with Contexts
- Shared processes
- Context switching
- Better resource utilization?

### Alternative: Microkernel Architecture
- Minimal core
- Pluggable execution engines
- Language-agnostic by design?

## API Evolution Paths

Current planned API is REST/WebSocket. Consider:

- GraphQL for complex queries?
- gRPC for performance?
- Native protocols (LSP, DAP)?