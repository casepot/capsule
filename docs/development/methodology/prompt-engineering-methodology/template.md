# Planning Prompt Template

Copy and fill out this template for any new planning task.

```markdown
# [Task Name] Planning Prompt

## Your Mission
You are tasked with planning [WHAT] that [KEY REQUIREMENT] while [CRITICAL CONSTRAINT].

## Context Gathering Requirements

Before planning, you MUST understand:

### 1. Problem History
- [What failed before]: [Why it failed]
- [Key lesson]: [What we learned]
- [Invariant]: [What cannot change]

### 2. Existing Infrastructure
- [Component]: [What it does] - [Can be used for]
- [Interface]: [How to connect]
- [Leverage point]: [Where to modify]

### 3. Constraints That Cannot Be Violated
- [Invariant]: [Consequence if broken]
- [Boundary]: [Why it exists]
- [Requirement]: [How to verify]

## Planning Methodology

### Phase 1: Analysis ([X]% effort)
<context_gathering>
Goal: [What to discover]
Stop when: [Completion criteria]
Depth: [How thorough]
</context_gathering>

### Phase 2: Solution Design ([Y]% effort)
Consider these approaches:
- **Approach A**: [Description]
  - Pros: [Benefits]
  - Cons: [Drawbacks]
  
- **Approach B**: [Description]
  - Pros: [Benefits]
  - Cons: [Drawbacks]

### Phase 3: Risk Assessment ([Z]% effort)
For each approach, identify:
- [Risk type]: [Mitigation strategy]
- [Failure mode]: [Detection method]

## Output Requirements

Your plan must include:

### 1. Executive Summary (5 sentences max)
- What changes
- Why it's safe
- How it maintains guarantees

### 2. Technical Approach
- Exact files and line numbers
- Precise code changes
- No ambiguity

### 3. Risk Mitigation
- How [invariant] is preserved
- Why [risk] cannot occur
- What errors users might see

### 4. Test Plan
- Test proving [core requirement]
- Test proving [no regression]
- Performance validation

## Calibration

<context_gathering>
- Search depth: [LOW/MEDIUM/HIGH]
- Maximum tool calls: [NUMBER/UNLIMITED]
- Early stop: [CONDITION]
</context_gathering>

## Non-Negotiables

1. [Requirement]: [Why critical]
2. [Constraint]: [What happens if violated]
3. [Invariant]: [How to preserve]

## Success Criteria

Before finalizing your plan, verify:
- [ ] [Specific requirement met]
- [ ] [Invariant preserved]
- [ ] [Risk mitigated]
- [ ] [Test defined]
- [ ] [Implementation clear]

## Additional Guidance

[Any specific hints, warnings, or domain knowledge]
```

## Quick Calibration Guide

### For Bug Fixes:
- Eagerness: LOW
- Specificity: HIGH  
- Tool budget: 5-10

### For Architecture:
- Eagerness: HIGH
- Specificity: MEDIUM
- Tool budget: 20-30

### For Performance:
- Eagerness: MEDIUM
- Specificity: HIGH
- Tool budget: 10-15

### For Security:
- Eagerness: HIGH
- Specificity: HIGH
- Tool budget: UNLIMITED