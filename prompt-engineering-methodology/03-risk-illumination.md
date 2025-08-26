# Phase 3: Risk Illumination

## Purpose
Identify failure modes before solution design. Every risk discovered during planning is one avoided during implementation.

## Risk Categories

### 1. Regression Risks
**What existing functionality might break?**
- Critical paths that must remain stable
- Performance characteristics to preserve
- API contracts that cannot change
- Test suites that must still pass

### 2. Architecture Risks
**What design decisions could destabilize the system?**
- Boundary violations
- Coupling increases
- Concurrency hazards
- Resource conflicts

### 3. Implementation Risks
**What could go wrong during coding?**
- Edge cases
- Error cascades
- State corruption
- Deadlock potential

### 4. Migration Risks
**What happens during transition?**
- Backward compatibility breaks
- Data migration failures
- Rollback complexity
- User disruption

## Risk Analysis Framework

### For Each Identified Risk:

```markdown
## Risk: [Name]

**Probability**: High | Medium | Low
**Impact**: Critical | Major | Minor
**Detection**: Easy | Moderate | Hard

**Scenario**: 
What sequence of events leads to this failure?

**Symptoms**:
- What would we observe?
- What errors would appear?
- What would break first?

**Mitigation**:
- Preventive: How to avoid it
- Detective: How to detect it early
- Corrective: How to recover if it happens
```

## Risk Discovery Techniques

### 1. Invariant Analysis
```
For each invariant:
- What maintains it?
- What could violate it?
- What depends on it?
```

### 2. Failure Mode Enumeration
```
For each component:
- How could it fail?
- What would it affect?
- Could it cascade?
```

### 3. Race Condition Hunting
```
For each shared resource:
- Who accesses it?
- Is access synchronized?
- What if ordering changes?
```

### 4. Error Path Tracing
```
For each error:
- How is it handled?
- Can handling fail?
- What if multiple errors occur?
```

## Example Application

From v0.2 planning:

```markdown
## Risk: Reintroducing Deadlock

**Probability**: Medium (if not careful)
**Impact**: Critical (system unusable)
**Detection**: Easy (tests timeout)

**Scenario**: 
Adding new reader for stdin → Two readers compete → Messages consumed by wrong reader → System deadlocks

**Mitigation**:
- Preventive: Maintain single-reader invariant
- Detective: Thread count monitoring
- Corrective: Timeout and restart

## Risk: Breaking Existing Tests

**Probability**: Low (with careful implementation)
**Impact**: Major (confidence loss)
**Detection**: Easy (CI fails)

**Mitigation**:
- Preventive: Run test suite frequently
- Detective: Automated CI pipeline
- Corrective: Revert changes
```

## Risk Prioritization Matrix

```
         Impact →
    ↓    Minor   Major   Critical
    High   [2]     [1]      [1]
    Med    [3]     [2]      [1]
    Low    [3]     [3]      [2]

Priority: [1] Must address, [2] Should address, [3] Accept risk
```

## Common Risk Patterns

### The Hidden Dependency
```
Change X → Breaks Y (not obviously connected)
Mitigation: Trace all dependencies before changing
```

### The Race Resurrection
```
Fix removes symptom → Root cause remains → Race returns elsewhere
Mitigation: Fix root cause, not symptoms
```

### The Performance Cliff
```
Small change → Crosses threshold → Catastrophic degradation
Mitigation: Benchmark before/after
```

### The Abstraction Leak
```
Internal detail exposed → Becomes API → Cannot change later
Mitigation: Explicit public/private boundaries
```

## Risk Communication

### In Planning Prompts:
```markdown
## Critical Risks
1. **[Risk Name]**: [One-line description]
   - Mitigation: [Specific action]

## Acceptable Risks
1. **[Risk Name]**: [Why it's acceptable]
```

### Clear Consequences:
- "If we do X, then Y will certainly happen"
- "Without Z, the system will deadlock"
- "This change requires updating all tests"

## Integration with Planning

Risk illumination provides:
1. **Non-negotiables**: "These risks are unacceptable"
2. **Guardrails**: "Stay within these boundaries"
3. **Validation requirements**: "Prove these risks are mitigated"
4. **Rollback triggers**: "If this happens, abort"

Early risk identification shapes solution design toward inherently safer approaches.