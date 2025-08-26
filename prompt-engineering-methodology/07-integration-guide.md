# Integration Guide: Assembling the Complete Planning Prompt

## Purpose
Combine all phases into a cohesive planning prompt that guides effective solution design while avoiding common pitfalls.

## Integration Formula

```
Planning Prompt = Context + Constraints + Guidance + Output Spec
                   ↑         ↑           ↑          ↑
              (Phases 1-2) (Phase 3) (Phases 4-6) (Phase 5)
```

## Standard Prompt Structure

### 1. Mission Statement
```markdown
# [Task Name] Planning Prompt

## Your Mission
You are tasked with planning [specific goal] that [key requirement] 
while [critical constraint].
```

### 2. Context Section (Phases 1-2)
```markdown
## Context

### Historical Context (Problem Archaeology)
- Previous attempt: [What failed and why]
- Lesson learned: [Key insight]
- Invariant discovered: [What cannot change]

### Existing Infrastructure (Architecture Recognition)  
- Available: [What already works]
- Leverage point: [Where to connect]
- Protocol/API: [Existing interfaces]
```

### 3. Constraints Section (Phase 3)
```markdown
## Constraints

### Non-Negotiable Requirements
1. [Invariant]: Must be maintained because [reason]
2. [Boundary]: Cannot cross because [consequence]

### Risks to Avoid
- [Risk]: Would cause [problem]
  Mitigation: [Specific action]
```

### 4. Solution Guidance (Phases 4, 6)
```markdown
## Planning Approach

### Solution Space
Consider these approaches:
- Approach A: [Description] - Best when [condition]
- Approach B: [Description] - Best when [condition]

### Calibration
<context_gathering>
Search depth: [Low/Medium/High]
Tool budget: [Number or unlimited]
Early stop: [Condition]
</context_gathering>
```

### 5. Output Requirements (Phase 5)
```markdown
## Output Requirements

Your plan must include:
1. **Approach Selection**: Which approach and why
2. **Implementation Steps**: File:line specific changes
3. **Risk Mitigation**: How invariants are preserved
4. **Test Strategy**: Specific validation approach
5. **Success Criteria**: Measurable outcomes
```

## Integration Patterns

### Pattern 1: Problem-First Integration
```
1. Start with failure analysis (Phase 1)
2. Show why previous approaches failed
3. Define constraints from failures
4. Guide toward different approach
```

Example:
```markdown
Previous attempts failed because of race conditions (two readers).
The single-reader invariant cannot be violated.
Therefore, solution must maintain exclusive stdin ownership.
```

### Pattern 2: Architecture-First Integration
```
1. Start with existing capabilities (Phase 2)
2. Show what's already available
3. Guide toward connection approach
4. Minimize new development
```

Example:
```markdown
The protocol already supports INPUT_REQUEST/input_response.
The await_input function already works correctly.
Therefore, connect input() to existing infrastructure.
```

### Pattern 3: Risk-First Integration
```
1. Start with unacceptable outcomes (Phase 3)
2. Define boundaries that prevent them
3. Guide solution within safe space
4. Validate risk mitigation
```

Example:
```markdown
Deadlock is unacceptable (system becomes unusable).
Multiple readers cause deadlock.
Therefore, maintain single-reader architecture.
```

## Cohesion Techniques

### Cross-Reference Between Sections
```markdown
As discovered in the historical context, [insight].
This existing infrastructure [component] addresses that.
To avoid the identified risk of [problem], we must [action].
```

### Progressive Refinement
```markdown
Given the context → Considering constraints → 
Within boundaries → Using this approach → 
Achieving these outcomes
```

### Explicit Connections
```markdown
Because [Phase 1 finding], we must [Phase 3 constraint],
which leads to [Phase 4 approach], validated by [Phase 5 test].
```

## Common Integration Mistakes

### 1. Phase Isolation
❌ Each section independent
✅ Sections reference each other

### 2. Redundant Information
❌ Repeating same facts
✅ Each section adds new perspective

### 3. Conflicting Guidance
❌ Context suggests A, constraints require B
✅ All sections align toward solution

### 4. Missing Connections
❌ Unused context information
✅ Every detail serves a purpose

## Quality Checklist

Before finalizing integrated prompt:

- [ ] Does context explain all constraints?
- [ ] Do constraints shape solution space?
- [ ] Does guidance reflect lessons learned?
- [ ] Are output requirements measurable?
- [ ] Is calibration appropriate for problem?
- [ ] Do all sections point toward solution?

## Example: Complete Integration

```markdown
# v0.2 Input Implementation Planning

## Your Mission
Plan the solution for v0.2 that enables input() functionality 
while preserving all v0.1 architectural improvements.

## Context
### Historical: v0's dual-reader architecture caused deadlocks
### Existing: INPUT_REQUEST protocol and await_input already work
### Gap: builtin.input not connected to protocol

## Constraints  
### Must Maintain: Single-reader invariant (no deadlocks)
### Must Not: Create new threads or readers
### Must Not: Break 29 passing tests

## Approach
### Consider: Builtin override vs. namespace injection
### Prefer: Minimal change leveraging existing infrastructure
### Depth: Low (solution space is small)

## Output Requirements
1. Exact file:line changes
2. Test proving input() works
3. Verification of no deadlock
```

## Iteration and Refinement

### After First Planning Attempt:
1. What context was missing?
2. What constraints were unclear?
3. What guidance was too vague?
4. What output was inadequate?

### Refine by:
- Adding missing historical context
- Clarifying ambiguous constraints
- Increasing specificity in guidance
- Tightening output requirements

## Final Validation

The integrated prompt succeeds when:
1. **Planner understands** the problem completely
2. **Solution respects** all constraints
3. **Approach leverages** existing infrastructure
4. **Output enables** immediate implementation
5. **Tests prove** requirements are met

This integration ensures all phases work together to produce an effective planning prompt.