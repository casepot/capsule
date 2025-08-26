# Session Reuse Pattern Implementation Planning Prompt

## Your Mission

You are tasked with fixing namespace persistence failures by implementing proper session reuse patterns. Currently, tests create new `Session()` instances for each test, which spawns new subprocesses with fresh namespaces. This breaks the fundamental expectation that variables, functions, and imports persist within a session.

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. Problem History (Problem Archaeology)
- **What Failed**: Variables defined in one execution don't exist in the next
- **Root Cause**: Each `Session()` creates a new subprocess via `asyncio.create_subprocess_exec`
- **Evidence**: pyrepl2 stores SessionContext and reuses: `self._sessions[session_id] = context`
- **Lesson**: Sessions must be reused, not recreated, to maintain persistent namespace

### 2. Existing Infrastructure (Architecture Recognition)
- **Session Class**: Located in `src/session/manager.py`, manages subprocess lifecycle
- **SessionPool**: Already exists in `src/session/pool.py` with acquire/release pattern
- **Subprocess Worker**: Maintains `self._namespace` dictionary for persistent state
- **Test Structure**: Tests in `test_foundation/` create new Session per test

### 3. Constraints That Cannot Be Violated (Risk Illumination)
- **Process Isolation**: Each session must remain in separate subprocess
- **Pool Efficiency**: Must maintain >80% hit rate after warmup
- **Resource Limits**: Cannot exceed max_sessions in pool
- **Test Independence**: Tests shouldn't interfere with each other

## Planning Methodology

### Phase 1: Analysis (40% effort)
<context_gathering>
Goal: Understand session lifecycle and why persistence fails
Stop when: You understand the relationship between Session, subprocess, and namespace
Depth: Examine Session.__init__, start(), and how tests use sessions
</context_gathering>

Investigate:
1. How `Session.start()` creates subprocess (line 106 in manager.py)
2. How pyrepl2 maintains SessionContext for reuse
3. Why SessionPool exists but isn't used in tests
4. The lifecycle of `self._namespace` in subprocess worker

### Phase 2: Solution Design (40% effort)

Consider these approaches:

**Approach A: Test Fixtures with Session Reuse**
- Create pytest fixtures that maintain session across tests in a class
- Session created once, reused for all tests
- Pros: Simple, minimal changes, follows pytest patterns
- Cons: Tests become order-dependent

**Approach B: Proper SessionPool Usage (Recommended)**
- Update tests to use `SessionPool.acquire()` and `release()`
- Pool maintains subprocess alive between acquisitions
- Pros: True session persistence, matches production usage
- Cons: More complex test setup

**Approach C: Session Registry Pattern**
- Create session registry that tracks and reuses sessions by ID
- Tests request sessions by ID rather than creating new
- Pros: Explicit session management
- Cons: Additional abstraction layer

### Phase 3: Risk Assessment (20% effort)
- **Risk**: Test pollution (one test affects another)
  - Mitigation: Clear namespace between test classes, not individual tests
- **Risk**: Resource leaks from unclosed sessions
  - Mitigation: Proper cleanup in pytest fixtures/teardown
- **Risk**: Deadlocks from pool exhaustion
  - Mitigation: Configure adequate pool size for tests

## Output Requirements

Your plan must include:

### 1. Executive Summary (5 sentences max)
- Why new Session() per test breaks namespace persistence
- How session reuse solves the problem
- Which approach you recommend and why
- Impact on test structure

### 2. Technical Approach

**For Approach A (Test Fixtures):**
```python
# test_foundation/conftest.py
@pytest.fixture(scope="class")
async def persistent_session():
    """Session that persists for entire test class."""
    session = Session()
    await session.start()
    yield session
    await session.shutdown()

# In tests
class TestNamespacePersistence:
    async def test_define_variable(self, persistent_session):
        await persistent_session.execute("x = 42")
    
    async def test_use_variable(self, persistent_session):
        result = await persistent_session.execute("x * 2")
        assert result.value == 84
```

**For Approach B (SessionPool):**
```python
# test_foundation/conftest.py
@pytest.fixture(scope="module")
async def session_pool():
    """Pool that maintains persistent sessions."""
    config = PoolConfig(min_idle=2, max_sessions=5)
    pool = SessionPool(config)
    await pool.start()
    yield pool
    await pool.shutdown()

# In tests
async def test_namespace_persistence(session_pool):
    session = await session_pool.acquire()
    try:
        await session.execute("x = 42")
        result = await session.execute("x * 2")
        assert result.value == 84
    finally:
        await session_pool.release(session)
```

### 3. Migration Strategy
1. Update test infrastructure (add fixtures)
2. Migrate tests incrementally
3. Verify namespace persistence works
4. Document new testing patterns

### 4. Test Plan
Create test that validates persistence:
```python
async def test_session_reuse_maintains_namespace():
    """Prove that reusing session preserves namespace."""
    pool = SessionPool(PoolConfig(min_idle=1))
    await pool.start()
    
    # First acquisition
    session = await pool.acquire()
    await session.execute("x = 100")
    await pool.release(session)
    
    # Second acquisition - SAME session
    session = await pool.acquire()
    result = await session.execute("x")
    assert result.value == 100
    
    await pool.shutdown()
```

## Calibration

<context_gathering>
- Search depth: MEDIUM (need to understand session lifecycle)
- Maximum tool calls: 10-15
- Early stop: When you understand Session-subprocess relationship
</context_gathering>

## Non-Negotiables

1. **Process Isolation**: Each session remains in separate subprocess
2. **Namespace Persistence**: Variables MUST persist within a session
3. **Test Clarity**: New pattern must be documented and clear
4. **No Global State**: Sessions remain independent

## Success Criteria

Before finalizing your plan, verify:
- [ ] Clear explanation of why new Session() breaks persistence
- [ ] Chosen approach maintains subprocess isolation
- [ ] Test pattern allows namespace persistence
- [ ] Migration path for existing tests is defined
- [ ] Pool configuration for tests is specified

## Additional Guidance

- Study how pyrepl2 uses SessionContext (implementations/base.py:149)
- SessionPool already has the infrastructure - focus on using it properly
- Consider test organization - group related tests that share namespace
- Document WHY session reuse is necessary for future developers
- Remember: The subprocess must stay alive to maintain namespace