# Architectural Invariants

## Single-Reader Invariant

The current implementation enforces that only one component reads from stdin. Investigate:

- `src/subprocess/worker.py:549-556` - How stdin is connected to the transport
- `src/subprocess/executor.py:86-118` - How input() is replaced with protocol messages

### Questions to Explore

1. What happens if two asyncio tasks try to read from the same StreamReader?
2. Could the protocol use separate file descriptors (like exec-py's FD separation)?
3. How does this constraint affect debugging and logging strategies?

## Protocol Ownership

The frame protocol owns stdin/stdout for Manager↔Worker communication. Consider:

- `src/protocol/transport.py` - MessageTransport implementation
- `src/protocol/framing.py` - Length-prefixed binary framing

### Investigation Points

- What would break if user code tried to read stdin directly?
- How does output capture work with threads vs async contexts?
- Could alternative transports (shared memory, sockets) relax this constraint?

## Namespace Isolation

Each subprocess maintains isolated namespace dictionary. Examine:

- `src/subprocess/worker.py:203-229` - Namespace initialization
- `src/subprocess/executor.py:172` - exec() with namespace parameter

### Trade-offs to Consider

- Memory overhead of deep copying for transactions
- Serialization challenges for checkpointing
- How would this work with compiled languages that don't have Python's namespace dict?

## Thread vs Async Execution

User code runs in threads while infrastructure is async. Study:

- `src/subprocess/executor.py:149-199` - Thread execution model
- `src/subprocess/worker.py:348-364` - Thread monitoring from async context

### Open Questions

- Could async code run directly in the worker's event loop?
- What are the implications for debugging and stack traces?
- How does this affect performance for I/O-bound vs CPU-bound code?