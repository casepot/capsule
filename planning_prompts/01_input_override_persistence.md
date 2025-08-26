# Input Override Persistence Fix Planning Prompt

## Your Mission

You are tasked with fixing a critical bug where the `input()` function override doesn't persist between executions. This causes user code that calls `input()` to fail with EOFError after the first execution. The fix is simple but must be implemented carefully to maintain system stability.

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. Problem History (Problem Archaeology)
- **What Failed**: After first execution, `input()` reverts to original stdin-reading function
- **Root Cause**: Line 199 in `src/subprocess/executor.py` restores `builtins.input = original_input`
- **Evidence**: exec-py successfully overrides input permanently at line 253: `local_ns["input"] = await_input`
- **Lesson**: Input override must persist in namespace, not be restored after each execution

### 2. Existing Infrastructure (Architecture Recognition)
- **ThreadedExecutor**: Runs user code in dedicated threads where blocking I/O is natural
- **create_protocol_input()**: Already creates thread-safe input function correctly
- **Protocol Messages**: INPUT/INPUT_RESPONSE messages work properly
- **Namespace**: Persistent dictionary where override should live permanently

### 3. Constraints That Cannot Be Violated (Risk Illumination)
- **Single-Reader Invariant**: Must not create additional stdin readers (causes deadlock)
- **Thread Safety**: Input function must remain thread-safe using asyncio.run_coroutine_threadsafe
- **Backward Compatibility**: All existing tests must continue passing
- **Namespace Integrity**: Must work with both dict and module-style __builtins__

## Planning Methodology

### Phase 1: Analysis (30% effort)
<context_gathering>
Goal: Understand current input override mechanism
Stop when: You fully understand why line 199 causes the bug
Depth: Read entire executor.py focusing on execute_code method
</context_gathering>

Investigate:
1. How `create_protocol_input()` creates the override function
2. Why the current code saves and restores original input
3. How exec-py avoids this problem (line 253)
4. The difference between modifying builtins vs namespace

### Phase 2: Solution Design (50% effort)

Consider these approaches:

**Approach A: Remove Restoration (Recommended)**
- Remove line 199: `builtins.input = original_input`
- Keep input override permanent in namespace
- Only create protocol input once if not already overridden
- Pros: Minimal change, follows exec-py pattern
- Cons: Global state modification (acceptable in subprocess isolation)

**Approach B: Namespace-Only Override**
- Don't modify builtins at all
- Only set `self._namespace["input"] = protocol_input`
- Pros: No global modification
- Cons: Won't work for code that imports builtins

### Phase 3: Risk Assessment (20% effort)
- **Risk**: Breaking existing code that expects original input
  - Mitigation: Check if already overridden before creating new one
- **Risk**: Memory leak from creating multiple input functions
  - Mitigation: Reuse existing override if present
- **Risk**: Incompatibility with different __builtins__ formats
  - Mitigation: Handle both dict and module cases

## Output Requirements

Your plan must include:

### 1. Executive Summary (5 sentences max)
- What line(s) will be removed/modified
- Why this fixes the persistence issue
- How it maintains thread safety
- Why it won't break existing functionality

### 2. Technical Approach
Exact changes needed:
- File: `src/subprocess/executor.py`
- Line 199: DELETE `builtins.input = original_input`
- Lines 159-161: MODIFY to check if override exists
- Add conditional: Only create protocol_input if not already in namespace

Example structure:
```python
# Only create protocol input if not already overridden
if "input" not in self._namespace or not callable(self._namespace.get("input")):
    protocol_input = self.create_protocol_input()
    self._namespace["input"] = protocol_input
    # Also set in builtins for exec context
    builtins.input = protocol_input
```

### 3. Risk Mitigation
- How single-reader invariant is preserved (no new threads/readers)
- Why removing restoration is safe (subprocess isolation)
- How backward compatibility is maintained (conditional creation)

### 4. Test Plan
Create test that proves persistence:
```python
async def test_input_persistence():
    session = Session()
    await session.start()
    
    # First execution with input
    await session.execute("name = input('Name: ')")  # Provide "Alice"
    
    # Second execution - input should still work
    await session.execute("age = input('Age: ')")  # Provide "30"
    
    # Verify both variables exist
    result = await session.execute("f'{name} is {age}'")
    assert result.value == "Alice is 30"
```

## Calibration

<context_gathering>
- Search depth: LOW (bug location is known)
- Maximum tool calls: 5-10
- Early stop: Once you confirm line 199 is the issue
</context_gathering>

## Non-Negotiables

1. **Must Not Create New Readers**: Maintain single-reader architecture
2. **Must Preserve Thread Safety**: Use existing asyncio.run_coroutine_threadsafe
3. **Must Pass All Tests**: No regression in existing functionality

## Success Criteria

Before finalizing your plan, verify:
- [ ] Line 199 removal is clearly specified
- [ ] Conditional override creation is implemented  
- [ ] Test proves input() persists across executions
- [ ] No new threads or readers are created
- [ ] All 29 existing tests still pass

## Additional Guidance

- Review how exec-py handles this at line 253 of runner_async.py
- The fix is genuinely simple - don't overthink it
- Focus on WHERE to make the change, not redesigning the system
- Remember: subprocess isolation makes global modification safe