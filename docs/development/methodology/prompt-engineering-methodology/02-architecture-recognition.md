# Phase 2: Architecture Recognition

## Purpose
Map the existing infrastructure to identify leverage points, connection opportunities, and sacred boundaries. The best solutions enhance rather than replace.

## Recognition Patterns

### 1. Infrastructure Inventory
**What already exists that we can use?**
- Protocol messages and handlers
- Communication channels
- State management systems
- Error handling pipelines
- Testing frameworks

### 2. Boundary Identification
**What separates components?**
- Process boundaries
- Thread boundaries
- Network boundaries
- Abstraction boundaries
- Ownership boundaries

### 3. Flow Tracing
**How does data move?**
- Input sources → Processing → Output sinks
- Control flow vs. data flow
- Synchronous vs. asynchronous paths
- Blocking vs. non-blocking operations

## Mapping Techniques

### Component Discovery
```python
# Find the actors
- Who sends messages?
- Who receives them?
- Who makes decisions?
- Who owns resources?
```

### Interface Analysis
```python
# Find the contracts
- What methods exist?
- What protocols are defined?
- What events are emitted?
- What responses are expected?
```

### Dependency Graphing
```
A → B: A depends on B
A ⇄ B: Bidirectional dependency
A ··> B: Optional dependency
A ==> B: Critical path
```

## Architecture Documentation Template

```markdown
## System Architecture

### Components
- **[Component]**: [Responsibility]
  - Owns: [Resources]
  - Provides: [Services]
  - Requires: [Dependencies]

### Communication Patterns
- [Pattern]: [Description]
  - Example: [Concrete usage]

### Critical Paths
1. [Operation]: [Start] → [Step] → [End]

### Leverage Points
- [Existing Feature]: Can be used for [New Purpose]
```

## Example Application

From v0.2 planning:
```markdown
### Discovered Infrastructure
- INPUT_REQUEST/input_response protocol: Already complete
- await_input function: Works via protocol
- Token management: Matches requests to responses
- Threading.Event: Bridges async/sync boundary

### Key Recognition
"The infrastructure is COMPLETE. Just not connected to builtins.input"

### Leverage Point
await_input already does what we need; redirect input() to use it
```

## Recognition Principles

### 1. Prefer Discovery Over Invention
Before designing new systems, thoroughly map what exists. Often the pieces are there, just disconnected.

### 2. Respect Existing Boundaries
Boundaries exist for reasons. Crossing them carelessly reintroduces old problems.

### 3. Follow Data, Not Structure
Organizational structure is less important than actual data flow. Trace the path of real operations.

### 4. Identify Pivot Points
Small changes at pivot points create large effects:
- Message routers
- Factory functions
- Initialization code
- Protocol handlers

## Common Patterns

### The Missing Link
Infrastructure exists at both ends but isn't connected:
```
[Working Feature A] ... gap ... [Working Feature B]
Solution: Simple connection code
```

### The Hidden Capability
Feature exists but isn't exposed:
```
Internal: Full implementation
External: No API
Solution: Add accessor
```

### The Parallel Path
Similar problem already solved elsewhere:
```
Context A: Solved with approach X
Context B: Same problem
Solution: Adapt approach X
```

## Integration with Planning

Architecture recognition provides:
1. **Infrastructure section**: "Here's what already works"
2. **Leverage points**: "Connect here for maximum effect"
3. **Boundaries**: "Don't cross these lines"
4. **Examples**: "Similar patterns already in codebase"

This ensures solutions build on solid foundations rather than starting from scratch.