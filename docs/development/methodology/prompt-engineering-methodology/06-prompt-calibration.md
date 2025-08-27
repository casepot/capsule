# Phase 6: Prompt Calibration

## Purpose
Tune the planner's autonomy, exploration depth, and decision-making based on problem characteristics and solution space size.

## Calibration Dimensions

### 1. Eagerness Level
**How proactive should the planner be?**

```markdown
## Low Eagerness (Focused)
<context_gathering>
- Search depth: very low
- Maximum tool calls: 2-5
- Early stop: When approach is obvious
</context_gathering>

Use when:
- Solution space is small
- Requirements are clear
- Time is critical

## High Eagerness (Exploratory)
<persistence>
- Keep exploring until all options mapped
- Don't stop at first solution
- Document all trade-offs
</persistence>

Use when:
- Solution space is large
- Requirements are complex
- Multiple stakeholders
```

### 2. Specificity Requirements
**How detailed should the output be?**

```markdown
## High Specificity
"In file X at line Y, change Z to W"
"Run command: npm test -- --coverage"
"Expected output: { status: 'success', count: 42 }"

## Medium Specificity  
"Modify the input handler to use protocol"
"Add tests for new functionality"
"Verify performance matches baseline"

## Low Specificity
"Implement input support"
"Ensure quality"
"Make it work"
```

### 3. Decision Authority
**What can the planner decide vs. defer?**

```markdown
## Full Authority
"Choose the best approach and plan complete implementation"
- Planner makes all technical decisions
- No approval gates

## Guided Authority
"Evaluate these 3 approaches and recommend one"
- Planner analyzes options
- Recommendation with rationale

## Limited Authority
"Plan implementation of Approach A specifically"
- Decision already made
- Planner provides execution details
```

## Calibration Patterns

### The Narrow Funnel
```
Start broad → Converge quickly → Single solution
Low eagerness + High specificity + Full authority

Example: "Find and fix the bug causing timeouts"
```

### The Wide Survey
```
Explore extensively → Map all options → Present choices
High eagerness + Medium specificity + Guided authority

Example: "Evaluate migration strategies for v3.0"
```

### The Precise Execution
```
Given approach → Detailed steps → Exact implementation
Low eagerness + High specificity + Limited authority

Example: "Implement the approved design document"
```

## Calibration by Problem Type

### Bug Fix
```yaml
Eagerness: Low (find root cause fast)
Specificity: High (exact fix location)
Authority: Full (fix it)
Tool Budget: 5-10 calls
Early Stop: When cause identified
```

### Architecture Design
```yaml
Eagerness: High (explore options)
Specificity: Medium (concepts over code)
Authority: Guided (recommend)
Tool Budget: 20-30 calls
Early Stop: Never (complete survey)
```

### Performance Optimization
```yaml
Eagerness: Medium (profile then fix)
Specificity: High (specific changes)
Authority: Full (optimize)
Tool Budget: 10-15 calls
Early Stop: When bottleneck found
```

### Security Audit
```yaml
Eagerness: High (thorough scan)
Specificity: High (exact vulnerabilities)
Authority: Limited (report only)
Tool Budget: Unlimited
Early Stop: Never (complete scan)
```

## Prompt Structure by Calibration

### Low Eagerness Template
```markdown
Find the specific issue quickly.
Maximum 5 tool calls.
Stop once you identify the fix.
Provide exact implementation.
```

### High Eagerness Template
```markdown
Thoroughly explore all approaches.
No limit on investigation depth.
Document every option found.
Compare all trade-offs.
```

### Balanced Template
```markdown
Investigate until confident.
Use judgment on depth needed.
Present 2-3 viable options.
Recommend with rationale.
```

## Dynamic Calibration

### Adjustment Triggers
```markdown
Increase eagerness if:
- Initial approach fails
- Requirements unclear
- Multiple failures found

Decrease eagerness if:
- Solution obvious
- Time critical
- Single point fix
```

### Feedback Loops
```markdown
If planner returns too vague:
→ Increase specificity requirement

If planner over-explores:
→ Add tool call budget

If planner misses options:
→ Increase eagerness
```

## Anti-Patterns

### Over-Calibration
❌ 15 different parameters to tune
✅ 3-4 key dimensions

### Under-Calibration
❌ Same prompt for all problems
✅ Adjusted per problem type

### Conflicting Calibration
❌ "Be thorough but use only 2 tools"
✅ Aligned constraints and goals

## Example Calibration

From v0.2 planning:

```markdown
## Calibration Decisions

**Eagerness**: Low
- Solution space is small (3 approaches max)
- Infrastructure exists (INPUT_REQUEST protocol)
- Connection point is clear

**Specificity**: High  
- Need exact file locations and line numbers
- Must specify precise code changes
- Clear test requirements

**Authority**: Full
- Choose approach (builtin override vs. namespace injection)
- Design implementation
- Define test strategy

**Result**: Focused, specific planning prompt that guides toward minimal solution
```

## Integration with Planning

Calibration provides:
1. **Search boundaries**: How much to explore
2. **Output requirements**: Level of detail needed
3. **Decision framework**: What to decide vs. defer
4. **Resource limits**: Tool calls, time, depth

This ensures the planning prompt produces output matched to the problem's needs.