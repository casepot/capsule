# Phase 1: Problem Archaeology

## Purpose
Excavate the problem's history to understand what has been tried, what failed, and why. This prevents repeating mistakes and reveals hidden constraints.

## Key Questions

### 1. Failure Forensics
- What solutions have been attempted?
- Why did each approach fail?
- What patterns emerge from failures?
- Were failures technical or architectural?

### 2. Evolution Timeline
- How did the problem evolve?
- What triggered each iteration?
- Which decisions were deliberate trade-offs?
- What assumptions proved incorrect?

### 3. Lesson Extraction
- What invariants were discovered through failure?
- Which constraints are physics vs. design choices?
- What complexity was essential vs. accidental?

## Archaeology Techniques

### Document Mining
```
Search for: README, CHANGELOG, migration guides, issue trackers
Look for: "known issues", "limitations", "trade-offs", "breaking changes"
Extract: Decisions and their rationales
```

### Code Fossil Analysis
```
Version comparison: v0 → v0.1 → current
Architecture shifts: What changed structurally?
Abandonment patterns: What code was deleted?
```

### Error Pattern Recognition
```
Test failures: What consistently breaks?
Timeout patterns: Where do deadlocks occur?
Race conditions: What requires synchronization?
```

## Output Template

```markdown
## Historical Context

### Previous Attempts
1. **[Approach Name]**
   - What: [Description]
   - Why Failed: [Root cause]
   - Lesson: [Key learning]

### Discovered Invariants
- [Invariant]: [Why it matters]

### Non-Negotiable Constraints
- [Constraint]: [Consequence if violated]
```

## Example Application

From v0.2 input planning:
- **v0 Attempt**: Dual readers (main + control thread)
- **Failure**: Race conditions, deadlocks after streaming
- **Lesson**: File descriptors are single-consumer resources
- **Invariant**: Single-reader architecture prevents races
- **Constraint**: stdin exclusively owned by protocol

## Anti-Patterns to Avoid

### 1. Assumption Archaeology
Don't assume why something failed. Find evidence in:
- Error messages
- Test failures
- Documentation
- Commit messages

### 2. Shallow Digging
Surface symptoms aren't root causes:
- "It times out" → Why? → "Deadlock" → Why? → "Two readers competing" → Why? → ...

### 3. Ignoring Success
Failed attempts often have working parts:
- v0 had working protocol messages
- Just needed different architecture

## Integration with Planning

The archaeology phase provides:
1. **Context section**: "Here's what failed before and why"
2. **Constraints section**: "These invariants cannot be violated"
3. **Risk awareness**: "Watch for these failure patterns"

This historical foundation ensures the planner doesn't repeat history.
