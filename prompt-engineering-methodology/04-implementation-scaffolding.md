# Phase 4: Implementation Scaffolding

## Purpose
Structure the solution space with clear boundaries, evaluation criteria, and implementation guidance. Transform abstract requirements into concrete approaches.

## Scaffolding Components

### 1. Solution Approaches
Define 2-3 distinct approaches with clear trade-offs:

```markdown
## Approach A: [Descriptive Name]
**Philosophy**: [Core idea in one sentence]
**Implementation**: [2-3 bullet points]
**Pros**: [Why choose this]
**Cons**: [Why avoid this]
**Best When**: [Ideal conditions]
```

### 2. Evaluation Criteria
How to choose between approaches:

```markdown
## Decision Matrix
| Criteria | Weight | Approach A | Approach B |
|----------|--------|------------|------------|
| Simplicity | 30% | High | Medium |
| Risk | 25% | Low | Medium |
| Performance | 20% | Good | Better |
| Maintainability | 25% | Excellent | Good |
```

### 3. Implementation Boundaries
What must not change:

```markdown
## Boundaries
### Must Preserve
- [Invariant]: [Why critical]

### Can Modify
- [Component]: [Within limits]

### Must Not Touch
- [System]: [Consequence if changed]
```

## Scaffolding Patterns

### The Minimal Delta
```python
# Smallest possible change
Current state → [Single modification] → Desired state

Example:
builtins.input = protocol_aware_input  # One line
```

### The Surgical Insert
```python
# Precise intervention at leverage point
System flow → [Intercept here] → Continue flow

Example:
Before exec() → Override input → Execute normally
```

### The Adapter Layer
```python
# Bridge between incompatible interfaces
Old interface → [Adapter] → New implementation

Example:
input() → ProtocolInput → INPUT_REQUEST
```

## Implementation Guidance Template

```markdown
## Implementation Guide

### Phase 1: Setup (10% effort)
1. [Specific action]
2. [Specific action]
Verify: [What should be true]

### Phase 2: Core Changes (70% effort)
1. File: [path], Line: [number]
   Change: [Exact modification]
   Reason: [Why here]

### Phase 3: Validation (20% effort)
1. Test: [What to verify]
   Expected: [Specific outcome]
```

## Concrete Specificity

### Instead of Vague:
❌ "Modify the input handling"
❌ "Update the protocol layer"
❌ "Fix the connection"

### Be Specific:
✅ "In runner_async.py line 250, add: builtins.input = await_input"
✅ "Replace sys.stdin with ProtocolStdin class"
✅ "Insert override before exec() call"

## Common Scaffolding Types

### 1. Override Pattern
```python
# Save original
original_x = thing.x
# Replace with new
thing.x = new_x
# Use system normally
# Restore if needed
```

### 2. Wrapper Pattern
```python
# Wrap existing functionality
class Enhanced(Original):
    def method(self):
        # Pre-processing
        result = super().method()
        # Post-processing
        return result
```

### 3. Injection Pattern
```python
# Inject into namespace
namespace['feature'] = implementation
# Code uses feature naturally
```

### 4. Protocol Pattern
```python
# Define interface
class Protocol:
    def operation(self): ...

# Multiple implementations
class ImplementationA(Protocol): ...
class ImplementationB(Protocol): ...
```

## Example Application

From v0.2 planning:

```markdown
## Approach A: Builtin Override
**Philosophy**: Route all input() through existing protocol
**Implementation**: 
- Line 250: Add builtins.input = await_input
- No other changes needed
**Pros**: Minimal, uses existing infrastructure
**Cons**: Global state modification
**Best When**: Subprocess isolation makes globals safe

## Approach B: Namespace Injection
**Philosophy**: Provide input via exec namespace
**Implementation**:
- Line 249: local_ns["input"] = await_input
**Pros**: No global modification
**Cons**: Won't catch input() in imports
```

## Quality Criteria

### Good Scaffolding:
- **Specific**: Line numbers, file paths, exact changes
- **Bounded**: Clear start and end
- **Testable**: Measurable outcomes
- **Reversible**: Can undo if needed

### Poor Scaffolding:
- **Vague**: "Fix the issue"
- **Unbounded**: "Refactor as needed"
- **Untestable**: "Should work better"
- **Irreversible**: "Delete old system"

## Integration with Planning

Implementation scaffolding provides:
1. **Concrete approaches**: Not just ideas but specific implementations
2. **Decision framework**: How to choose between options
3. **Step-by-step guidance**: Exact sequence of changes
4. **Verification points**: How to know it's working

This transforms high-level requirements into actionable implementation plans.