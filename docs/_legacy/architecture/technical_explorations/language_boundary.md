# Language Boundary Exploration

## Current Python-Specific Components

Examine what makes these components Python-specific:

- `src/subprocess/worker.py:421-455` - AST parsing and source tracking
- `src/subprocess/executor.py:168-182` - Python's compile() and exec()
- `src/subprocess/checkpoint.py` - Cloudpickle serialization

## Language-Agnostic Components

These components appear to have no Python dependencies:

- `src/protocol/messages.py` - Message definitions
- `src/protocol/framing.py` - Binary frame protocol
- `src/protocol/transport.py` - Transport layer
- `src/session/pool.py` - Process pooling logic
- `src/session/manager.py:106-113` - Subprocess spawning

### Investigation Questions

1. Where exactly is the boundary? Is it at the subprocess spawn command?
2. How much of the protocol assumes Python semantics (like "namespace")?
3. Could `ExecuteMessage.code` carry a language hint?

## Language-Specific Challenges

### JavaScript Worker Considerations

- How would V8 isolates map to subprocess model?
- Native async support - no thread needed?
- Module system complexities

### Haskell Worker Considerations  

- Lazy evaluation - when to force thunks?
- Type information - should protocol carry types?
- GHCi already has a protocol - adapt or replace?

## Protocol Extensions to Explore

Consider what protocol changes might be needed:

```python
# Current - in src/protocol/messages.py:42
code: str = Field(description="Python code to execute")

# Potential investigation areas:
# - Language field?
# - Evaluation strategy hints?
# - Type annotations?
```

## Implementation Paths to Research

1. **Subprocess Command Pattern**
   - Look at how `src/session/manager.py:107` spawns Python
   - Could this be parameterized by language config?

2. **Message Routing**
   - Trace message flow from API to worker
   - Where would language routing happen?

3. **State Serialization**
   - How would non-Python languages handle checkpoint/restore?
   - Is cloudpickle assumption too restrictive?