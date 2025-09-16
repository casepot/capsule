# Evaluation Strategies Across Languages

## Python's Eager Evaluation

PyREPL3 currently assumes Python's eager evaluation:

- `src/subprocess/executor.py:172` - exec() evaluates immediately
- Results available right after execution
- Side effects happen in order

## Lazy Evaluation Considerations

GHCi demonstrates different evaluation needs:

### Thunk Preservation
- Values not evaluated until needed
- `:sprint` shows thunk structure without forcing
- `:force` explicitly evaluates

### Questions for PyREPL3

1. Could Python benefit from lazy patterns?
2. How would generators/iterators be handled?
3. Should protocol distinguish evaluation strategies?

## Strict Mode Patterns

Haskell's `-XStrict` pragma shows module-level control:
- Automatic strictness annotations
- WHNF vs full evaluation
- Module-scoped changes

### Potential PyREPL3 Explorations

- Execution hints in protocol?
- Per-session evaluation strategies?
- Language-specific defaults?

## Protocol Implications

Current `ExecuteMessage` has minimal control:

```python
# From src/protocol/messages.py
code: str
capture_source: bool
transaction_policy: TransactionPolicy
```

### Potential Strategy Fields

Consider what strategies might need:
- `evaluation_strategy`: "eager" | "lazy" | "whnf"
- `force_results`: bool
- `timeout_behavior`: "force" | "suspend" | "error"

## Multi-Language Strategy Handling

### JavaScript
- Eager but with Promise/async semantics
- How to handle pending promises?
- When to resolve vs return promise?

### Haskell  
- Lazy by default
- Need thunk representation in protocol?
- Special messages for inspection vs evaluation?

### SQL
- Set-based operations
- Query plan vs execution
- EXPLAIN vs SELECT

## Implementation Investigation

1. **AST Analysis**: Could we detect lazy constructs?
   - Generators
   - Iterators  
   - Async generators
   - functools.partial

2. **Result Handling**: When to materialize?
   - list(generator) vs return generator
   - Streaming vs buffering
   - Memory considerations

3. **Debugging Support**: Non-forcing inspection?
   - sys.getsizeof without evaluation?
   - Representation without side effects?
   - Stack trace without unwinding?

## Performance Trade-offs

Consider benchmarking:

- Eager evaluation overhead for unused values
- Lazy evaluation thunk creation cost
- Memory usage patterns
- Debugging complexity

## Open Questions

1. Should evaluation strategy be per-session or per-execution?
2. How would checkpoint/restore handle unevaluated thunks?
3. Can we mix evaluation strategies in one namespace?
4. What would "lazy Python" even mean in practice?