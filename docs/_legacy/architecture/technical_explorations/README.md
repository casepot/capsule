# Technical Explorations

This directory contains focused explorations of specific technical threads in PyREPL3's design. These documents are intended to provoke investigation and thought rather than prescribe solutions.

## Documents

### [Architectural Invariants](./architectural_invariants.md)
Explores the fundamental constraints that shape PyREPL3's design:
- Single-reader invariant for stdin
- Protocol ownership of I/O streams
- Namespace isolation patterns
- Thread vs async execution split

### [Language Boundary](./language_boundary.md)
Investigates the separation between language-agnostic and language-specific components:
- Current Python dependencies
- Potential abstraction points
- Multi-language protocol needs
- Worker interface design

### [Concurrency Patterns](./concurrency_patterns.md)
Examines concurrent execution and deadlock patterns:
- The third task blocking problem
- Lock-free task creation patterns
- Sync/async context bridging
- Event loop management

### [Async Execution Models](./async_execution_models.md)
Analyzes approaches to async code execution:
- Current thread-based model
- Top-level await possibilities
- AST detection strategies
- Performance implications

### [Beyond REPL](./beyond_repl.md)
Questions the REPL paradigm and explores execution service patterns:
- REPL limitations (Read/Eval/Print/Loop)
- Session-oriented RPC patterns
- Alternative execution models
- Service architecture possibilities

### [Evaluation Strategies](./evaluation_strategies.md)
Compares evaluation strategies across languages:
- Python's eager evaluation
- Lazy evaluation (Haskell/GHCi)
- Strict mode patterns
- Protocol implications

### [Implementation Archaeology](./implementation_archaeology.md)
Documents the implementation history and lessons learned:
- The three critical issues
- Failed approaches
- Design constraints discovered
- Questions for future investigation

## How to Use These Documents

1. **Start with the code**: Each document references specific source files to examine
2. **Question assumptions**: These explorations present possibilities, not prescriptions
3. **Investigate deeply**: Use the questions as starting points for your own exploration
4. **Document findings**: Add your own explorations as you discover new patterns

## Contributing

When adding new explorations:
- Keep documents focused on a single technical thread
- Reference specific code locations
- Pose questions rather than mandate solutions
- Include trade-offs and alternatives
- Avoid prescriptive language