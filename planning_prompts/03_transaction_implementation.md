# Transaction Support Implementation Planning Prompt

## Your Mission

You are tasked with implementing transaction support for code execution, allowing namespace changes to be rolled back on failure or committed on success. The message types and enums exist (`TransactionPolicy`), but the actual transaction logic is not implemented. This feature is critical for safe experimentation and error recovery.

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. Problem History (Problem Archaeology)
- **Current State**: ExecuteMessage has `transaction_policy` field, but it's ignored
- **Evidence**: exec-py successfully implements transactions with namespace snapshots (lines 211, 268-270)
- **Pattern**: exec-py uses simple dict copy: `op.ns_snapshot = {k: v for k, v in self._global_ns.items()}`
- **Lesson**: Transactions can be simple namespace snapshots without complex machinery

### 2. Existing Infrastructure (Architecture Recognition)
- **TransactionPolicy Enum**: COMMIT_ALWAYS, COMMIT_ON_SUCCESS, ROLLBACK_ON_FAILURE, EXPLICIT
- **ExecuteMessage**: Already has `transaction_policy` field
- **Namespace**: `self._namespace` dictionary in worker.py can be snapshot/restored
- **ThreadedExecutor**: Executes code and can detect exceptions

### 3. Constraints That Cannot Be Violated (Risk Illumination)
- **Memory Limits**: Snapshots could be large (numpy arrays, dataframes)
- **Atomicity**: Changes must be all-or-nothing
- **Performance**: Snapshot overhead must be acceptable
- **Nested Transactions**: Initially disallow for simplicity

## Planning Methodology

### Phase 1: Analysis (30% effort)
<context_gathering>
Goal: Understand namespace lifecycle and exception handling
Stop when: You know exactly where to snapshot and restore
Depth: Study worker.py handle_execute and executor.py execute_code
</context_gathering>

Investigate:
1. How exec-py creates snapshots (runner_async.py:211)
2. Where exceptions are caught in current execution flow
3. What makes a "successful" vs "failed" execution
4. Memory implications of dictionary copies

### Phase 2: Solution Design (50% effort)

Consider these approaches:

**Approach A: Simple Dictionary Snapshot (Recommended)**
- Before execution: `snapshot = dict(self._namespace)`
- On failure + rollback policy: `self._namespace.clear(); self._namespace.update(snapshot)`
- Pros: Simple, proven by exec-py, easy to debug
- Cons: Memory overhead, doesn't handle external state

**Approach B: Copy-on-Write Pattern**
- Track only changed keys during execution
- Restore only modified values on rollback
- Pros: Memory efficient
- Cons: Complex tracking logic, harder to debug

**Approach C: Checkpoint-Based Transactions**
- Reuse checkpoint system for transaction snapshots
- Pros: Unified mechanism, handles complex objects
- Cons: Overhead, unnecessary complexity for simple cases

### Phase 3: Risk Assessment (20% effort)
- **Risk**: Out of memory with large objects
  - Mitigation: Set snapshot size limits, fail gracefully
- **Risk**: External state not rolled back (files, network)
  - Mitigation: Document limitation clearly
- **Risk**: Partial execution before exception
  - Mitigation: Ensure atomicity at Python execution level

## Output Requirements

Your plan must include:

### 1. Executive Summary (5 sentences max)
- Where snapshots will be created
- How rollback will restore state
- Which transaction policies will be supported
- Performance impact assessment

### 2. Technical Approach

Implement in `src/subprocess/worker.py`:

```python
async def handle_execute(self, message: ExecuteMessage) -> None:
    """Handle execute message with transaction support."""
    
    # Create snapshot if policy requires it
    snapshot = None
    if message.transaction_policy != TransactionPolicy.COMMIT_ALWAYS:
        # Deep copy to handle mutable objects
        snapshot = dict(self._namespace)
    
    try:
        # Create and run executor
        executor = ThreadedExecutor(...)
        
        # ... execution logic ...
        
        if hasattr(executor, '_error') and executor._error:
            raise executor._error
        
        # SUCCESS - apply transaction policy
        if message.transaction_policy == TransactionPolicy.COMMIT_ON_SUCCESS:
            pass  # Changes already in namespace
        elif message.transaction_policy == TransactionPolicy.EXPLICIT:
            # Could mark for manual commit later
            pass
        
    except Exception as e:
        # FAILURE - apply transaction policy
        if message.transaction_policy == TransactionPolicy.ROLLBACK_ON_FAILURE:
            if snapshot is not None:
                # Restore snapshot
                self._namespace.clear()
                self._namespace.update(snapshot)
                # Restore builtins
                import builtins
                self._namespace["__builtins__"] = builtins
        
        # Send error message
        # ...
```

### 3. Policy Specifications

Define exact behavior for each policy:

**COMMIT_ALWAYS** (default):
- No snapshot created
- All changes persist regardless of success/failure
- Lowest overhead

**COMMIT_ON_SUCCESS**:
- Snapshot created
- Changes persist only if no exception
- Rollback on any exception

**ROLLBACK_ON_FAILURE**:
- Snapshot created  
- Changes persist on success
- Rollback on exception

**EXPLICIT**:
- Snapshot created
- Changes held pending explicit commit
- Future: Add commit/rollback messages

### 4. Test Plan

```python
async def test_rollback_on_failure():
    """Test that namespace rolls back on exception."""
    session = Session()
    await session.start()
    
    # Set initial state
    await session.execute("x = 10; y = 20")
    
    # Execute with rollback policy - will fail
    message = ExecuteMessage(
        id="tx-1",
        timestamp=0,
        code="x = 30; y = 40; z = 50; raise ValueError('test')",
        transaction_policy=TransactionPolicy.ROLLBACK_ON_FAILURE
    )
    
    try:
        await session.execute(message)
    except:
        pass  # Expected
    
    # Verify rollback
    result = await session.execute("(x, y, 'z' in dir())")
    assert result.value == (10, 20, False)  # x, y restored, z doesn't exist
```

## Calibration

<context_gathering>
- Search depth: MEDIUM (need to understand execution flow)
- Maximum tool calls: 10-15
- Early stop: When you find where to add snapshot logic
</context_gathering>

## Non-Negotiables

1. **Atomicity**: Transactions must be all-or-nothing
2. **No Nested Transactions**: Initially disallow for simplicity
3. **Preserve Builtins**: Always restore __builtins__ after rollback
4. **Memory Safety**: Handle large namespace gracefully

## Success Criteria

Before finalizing your plan, verify:
- [ ] Snapshot creation point identified
- [ ] Rollback mechanism specified
- [ ] All 4 policies have clear behavior
- [ ] Memory implications addressed
- [ ] Test proves rollback works

## Additional Guidance

- Start with exec-py's simple approach (runner_async.py:211, 268-270)
- Don't over-engineer - dict copy is sufficient initially
- Focus on the ROLLBACK_ON_FAILURE case first
- Consider using copy.deepcopy for nested structures
- Document limitations (external state not rolled back)
- Remember: Perfect is the enemy of good - simple solution first