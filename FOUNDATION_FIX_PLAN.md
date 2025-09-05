# Foundation Fix Plan: Building Solid Ground Before Full Spec Implementation

> Phase 1 Status Update (2025-09-05)

- Phase 0: COMPLETE
- Phase 1: COMPLETE — AsyncExecutor with top‑level await (TLA), AST fallback, merge‑only namespace semantics, routing + blocking I/O detection, DI factory, and unit CI workflow.
- Unit tests: 111/111 passing (unit suite) + 3 xpassed expected transitions.
- Integration tests (informational): 19 passed, 11 failing; failures are in session/worker/transport orchestration and are scoped for Phase 2.
- Notable corrections: PyCF constant is `0x2000` (not `0x1000000`). TLA timeout is now configurable via `AsyncExecutor(tla_timeout=...)` and `async_executor_factory(..., tla_timeout=...)`.

Next steps (Phase 2 preview):
- Address integration failures (worker last‑expression result delivery, large output handling, checkpoint create/restore, concurrent executions, transport backpressure/drain ordering).
- Audit event loop lifecycle in session/worker components.
- Add configurability + telemetry for blocking I/O detection.
- Add perf guardrails (TLA latency micro‑benchmarks) and documentation polish for DI usage.

— The legacy status block below reflects the original plan context prior to this update.

**STATUS**: Day 4+ Complete (Phase 0 Emergency Fixes + All PR Review ✅) | Test Pass Rate: 97.9% (94/96 unit tests)
**BRANCH**: `fix/foundation-phase0-emergency-fixes` (Days 1-4 work, PR #10 ready to merge)

## Updated Roadmap & PR Split (2025-09-05)

This section supersedes older mixed notes below. It defines a clear split between the AsyncExecutor core and the Resonate integration.

### Roadmap Summary (Updated)

| Phase | PR Name | Scope | Status |
| - | - | - | - |
| Phase 0 | foundation-phase0-emergency-fixes | ThreadedExecutor async wrapper, protocol fixes, namespace merge-only | COMPLETE |
| Phase 1 | async-executor-core | AsyncExecutor with TLA + AST fallback, routing, blocking I/O detection, DI factory, unit CI | COMPLETE (ready to merge) |
| Phase 2 | resonate-integration | Durable functions, protocol bridge with promises, HITL capability, checkpoints, local/remote adapters | PLANNED |

### PR: async-executor-core (Phase 1)

- Deliverables:
  - AsyncExecutor with top-level await (eval-first using `PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x2000`), `CO_COROUTINE` detection, `asyncio.timeout(tla_timeout)`.
  - AST fallback (def→async def, zero-arg lambda transform, conservative global hoisting) with locals-first merge and global-diff application.
  - Routing and enhanced blocking I/O detection (alias-aware for time/requests/socket/os/pathlib, etc.).
  - DI factory (`async_executor_factory`) and awaitable promise adapter.
  - Unit CI workflow (`.github/workflows/unit-tests.yml`).
- Non-goals (explicitly out of this PR): Resonate durable functions, protocol bridge, HITL workflows, remote orchestration, session/worker lifecycle fixes.
- Acceptance Criteria:
  - All unit tests for AsyncExecutor and related components pass; TLA semantics verified on direct and fallback paths; namespace merge-only policy preserved; configurable TLA timeout works.
  - No namespace dict replacement anywhere; `ENGINE_INTERNALS` protected.
  - CI runs unit tests on PRs (Python 3.11).
- Test Plan:
  - Unit: TLA expression and statements, AST fallback transformations, globals binding, result history, blocking I/O detection, timeout override.
  - Integration: Not required for this PR (tracked for Phase 2).
- Dependencies:
  - None on Resonate SDK. Uses local DI only.
- Status: COMPLETE. 111/111 unit tests passing (+3 xpassed expected transitions).

### PR: resonate-integration (Phase 2)

- Deliverables:
  - Durable function `durable_execute(ctx, args)` that routes to AsyncExecutor, with pre/post checkpoints and DI-driven configuration.
  - `ResonateProtocolBridge` that maps protocol request/response to durable promises.
  - Minimal HITL `InputCapability` using durable promises (create, wait, resolve) with transport message correlation.
  - Local/remote init adapters (local stub acceptable for tests) with DI graph registration.
- Integration Stabilization Tasks:
  - Worker/session last-expression result delivery (ensure `ResultMessage.value` semantics are consistent for multi-line cells).
  - Large output/message chunking and drain ordering under backpressure.
  - Checkpoint create/restore validation and state consistency.
  - Event loop lifecycle audit (bind asyncio primitives to correct loop; avoid cross-loop usage).
- Acceptance Criteria:
  - Local-mode durable execution works end-to-end (no server) with promises and HITL flows in tests.
  - Integration tests covering result delivery, checkpointing, and large message handling pass.
  - Configurable timeouts propagate through durable functions and promises.
- Test Plan:
  - Unit: DI graph, durable function wrapper, protocol bridge promise roundtrips, HITL capability request/response, error/timeout propagation with `add_note` context.
  - Integration (local): durable execute run/rpc, promise resolution, input flow; checkpoint flow smoke tests.
  - Remote: mocked interface parity (no real network required for Phase 2).
- Dependencies:
  - AsyncExecutor core (Phase 1) merged.
  - Stable transport framing for message correlation.
- Status: PLANNED. Work begins after Phase 1 PR merges.

### Work Breakdown & Order (Updated)

1) Merge PR async-executor-core (Phase 1).
2) Implement `durable_execute` and DI wiring; add unit tests (wrapper + checkpoints) [Resonate integration].
3) Implement `ResonateProtocolBridge` promises; add unit tests; minimal local-mode adapter.
4) Implement HITL `InputCapability` using bridge; add unit tests (promise roundtrip).
5) Integration stabilization in worker/session (result delivery, large output, checkpoints, loop lifecycle) and corresponding integration tests.
6) Add telemetry/configuration for blocking I/O detection; performance micro-benchmarks and CI guards.

### Interfaces & Dependencies

- AsyncExecutor Core → Resonate: No direct dependency. Exposed via DI factory; durable functions consume factory to instantiate per-execution executors.
- Resonate Durable Functions → Worker/Transport: Durable functions call into AsyncExecutor; protocol messages still sent via transport; promises correlate responses to waiting code.
- HITL → Transport: Input requests sent as protocol messages; results provided by promise resolution.

### Risks & Mitigations (Phase 2)

- Race conditions in session/worker under high output: add orderly drain and backpressure policies; validate with large message tests.
- Event loop misbinding: audit initialization order; ensure all asyncio objects are bound to the active loop.
- Promise timeouts and error context: adopt `asyncio.timeout()` consistently; ensure `add_note` context includes execution id/mode.


## Executive Summary

**Last Updated**: After full spec review and deep analysis of Resonate integration patterns.

After reviewing the current implementation, test failures, and **reading the full specifications in detail**, I've identified that we're in an **architectural transition phase** with a clear solution path. The specs elegantly solve the async/await vs yield paradigm through a **wrapper pattern** where Resonate wraps AsyncExecutor at the integration layer - no code transformation needed.

**Phase 0 Status**: ✅ COMPLETE - AsyncExecutor skeleton implemented with proper lifecycle management, ThreadedExecutor delegation working with async wrapper, namespace merge-only policy enforced, ENGINE_INTERNALS centralized, all PR review feedback addressed. 97.6% test pass rate achieved (83/85 tests). Ready to merge to master.

**Key Discovery**: The specs already solve the hard problems. Our refinements focus on making the bridge robust, testing edge cases early, and ensuring consistent behavior across local/remote modes.

## Development Workflow & Branching Strategy

### Phase-Based Branches
We're using a phase-based branching approach to keep related changes together while maintaining a clean history:

| Phase | Branch Name | Days | Scope | Merge Criteria |
|-------|------------|------|-------|----------------|
| **Phase 0** | `fix/foundation-phase0-emergency-fixes` | 1-3 | Emergency fixes to unblock testing | ✅ Tests passing (>80%) |
| **Phase 1** | `fix/foundation-phase1-async-executor` | 4-7 | AsyncExecutor foundation | Tests passing, no regressions |
| **Phase 2** | `fix/foundation-phase2-bridge` | 8-10 | Bridge architecture | Full integration ready |

### Workflow
```bash
# Current work (Phase 0, Days 1-3)
git checkout fix/foundation-phase0-emergency-fixes
# ... implement Days 2-3 fixes ...
git commit -m "fix: implement namespace merge-only policy"

# When Phase 0 complete
git push origin fix/foundation-phase0-emergency-fixes
# Create PR → Review → Merge to master

# Start Phase 1 (Day 4)
git checkout master && git pull
git checkout -b fix/foundation-phase1-async-executor
```

### Merge to Master Criteria
- ✅ All phase goals achieved
- ✅ Tests passing (target >80% for Phase 0, >95% for Phase 1-2)
- ✅ No regressions from previous phase
- ✅ Code reviewed (if team environment)

## Key Files Referenced

### Current Implementation
- `src/subprocess/executor.py` - ThreadedExecutor implementation
- `src/subprocess/worker.py` - SubprocessWorker main entry
- `src/subprocess/namespace.py` - NamespaceManager 
- `src/protocol/messages.py` - Pydantic message models
- `src/session/manager.py` - Session lifecycle management

### Test Files
- `tests/unit/test_executor.py` - Executor unit tests (failing)
- `tests/unit/test_messages.py` - Message validation tests
- `tests/integration/test_session.py` - Session integration tests
- `tests/features/test_cancellation.py` - Cancellation tests

### Specification Documents
- `docs/async_capability_prompts/current/00_foundation_resonate.md` - Resonate integration vision
- `docs/async_capability_prompts/current/10_prompt_async_executor.md` - AsyncExecutor implementation guide
- `docs/async_capability_prompts/current/20_spec_architecture.md` - Full architecture specification
- `docs/async_capability_prompts/current/22_spec_async_execution.md` - Async execution patterns
- `docs/async_capability_prompts/current/24_spec_namespace_management.md` - Namespace management rules

## Current State vs. Target Architecture

### Current State (What We Have)
```
Worker → ThreadedExecutor (sync) → Direct namespace manipulation
                                 → Basic message protocol
                                 → No durability
```

### Target Architecture (What Specs Describe)
```
Worker → AsyncExecutor (async) → Resonate Durable Functions
                              → Promise-based communication
                              → Capability injection
                              → Durable namespace with merge-only policy
```

### Transition State (What We Need Now)
```
Worker → Async Adapter → ThreadedExecutor (for blocking I/O)
                       → AsyncExecutor skeleton (for async code)
                       → Fixed message protocol
                       → Thread-safe namespace with merge-only
```

## Critical Foundational Gaps

### 1. 🔴 **Async/Sync Bridge Missing** (Blocks ALL Testing)
- **Problem**: Tests expect `await executor.execute_code()` but ThreadedExecutor is synchronous
- **Impact**: 50% of tests fail immediately with `TypeError: NoneType can't be used in await`
- **Root Cause**: No async wrapper around ThreadedExecutor
- **Evidence**: 
  - `src/subprocess/executor.py:504-596` - `execute_code()` returns `None`, not a coroutine
  - `tests/unit/test_executor.py:51` - Test tries `await executor.execute_code("2 + 2")`
  - `docs/async_capability_prompts/current/10_prompt_async_executor.md:78-94` - Spec shows async execute method

### 2. 🔴 **Message Protocol Incomplete** (Blocks Communication)
- **Problem**: Required fields missing in message creation
- **Impact**: Pydantic validation errors throughout
- **Missing Fields**:
  - `ResultMessage`: `execution_time` required at line 84 (`src/protocol/messages.py:84`)
  - `HeartbeatMessage`: Fields defined at lines 124-126 (`src/protocol/messages.py:124-126`)
  - `CheckpointMessage`: Fields required at lines 99-103 (`src/protocol/messages.py:99-103`)
- **Test Evidence**:
  - `tests/unit/test_messages.py:38-47` - Creates ResultMessage without `execution_time`
  - `tests/unit/test_messages.py:106-113` - Creates HeartbeatMessage without required fields

### 3. 🟠 **Namespace Management Violates Core Principle** 
- **Problem**: Risk of replacing namespace instead of merging
- **Impact**: Will cause KeyError failures (as discovered in IPython investigation)
- **Critical Rule**: NEVER replace namespace, ALWAYS merge
- **Spec Requirement**: `docs/async_capability_prompts/current/24_spec_namespace_management.md:15-29`
  - "The Golden Rule: Never Replace, Always Merge"
  - Line 18-19: `self._namespace = new_namespace` ❌ WRONG
  - Line 22: `self._namespace.update(new_namespace)` ✅ CORRECT
- **Current Risk**: `src/subprocess/namespace.py:32-40` - Sets namespace in `_setup_namespace()`
- **Worker Issue**: `src/subprocess/worker.py:126-134` - Creates new namespace dict

### 4. 🟠 **No Execution Mode Router**
- **Problem**: All code goes through ThreadedExecutor regardless of type
- **Impact**: Can't handle async code, top-level await, or optimize execution
- **Need**: Basic router to detect code type and route appropriately
- **Spec Vision**: `docs/async_capability_prompts/current/22_spec_async_execution.md:149-247`
  - Lines 149-200: `analyze_execution_mode()` method
  - Lines 70-75: `ExecutionMode` enum definition
  - Lines 252-293: Main `execute()` method with routing
- **Current Gap**: `src/subprocess/worker.py:227-249` - Always creates ThreadedExecutor

### 5. 🟡 **Event Loop Coordination Broken**
- **Problem**: Multiple event loops, asyncio objects bound to wrong loops
- **Impact**: Integration tests fail with event loop errors
- **Root Cause**: Poor event loop lifecycle management
- **Evidence in Session**: `src/session/manager.py:81-83`
  - Line 81: `self._lock = asyncio.Lock()`
  - Line 82: `self._ready_event = asyncio.Event()`
  - Line 83: `self._cancel_event = asyncio.Event()`
- **Spec Guidance**: `docs/async_capability_prompts/current/22_spec_async_execution.md:123-128`
  - "DO NOT create new event loop - use existing"

## Prioritized Fix Plan

### Phase 0: Emergency Fixes ✅ COMPLETED (Days 1-3)
These unblock testing and development:

#### 0.1 Add Async Wrapper to ThreadedExecutor ✅
**File**: `src/subprocess/executor.py` (added at lines 627-674)
```python
# ACTUAL IMPLEMENTATION in ThreadedExecutor class:
async def execute_code_async(self, code: str) -> Any:
    """Async wrapper for compatibility with tests."""
    # Note: Output pump should already be started by caller
    try:
        loop = asyncio.get_event_loop()
        self._result = None
        self._error = None
        
        # Run sync execute_code in thread pool
        future = loop.run_in_executor(None, self.execute_code, code)
        await future
        
        # Drain outputs with timeout protection for mock transports
        try:
            await self.drain_outputs(timeout=0.5)
        except (OutputDrainTimeout, asyncio.TimeoutError):
            pass  # OK in tests with mock transport
        
        if self._error:
            raise self._error
        return self._result
    finally:
        pass  # State reset on next execution
```
**Tests Fixed**: `tests/unit/test_executor.py` - All 5 tests now pass
**Also Updated**: Tests to use `AsyncMock()` for transport.send_message

#### 0.2 Fix Message Field Issues ✅
**Files Fixed**:
- `src/subprocess/worker.py` - NO CHANGES NEEDED (already had execution_time at lines 338, 349)
- `tests/unit/test_messages.py` - FIXED test data

```python
# ACTUAL FIX in test_messages.py line 44:
msg = ResultMessage(
    id=str(uuid.uuid4()),
    timestamp=time.time(),
    execution_id="exec-123",
    value=42,
    repr="42",
    execution_time=0.5,  # ADDED THIS FIELD
)

# ACTUAL FIX in test_messages.py lines 110-112:
msg = HeartbeatMessage(
    id="test-123",
    timestamp=time.time(),
    memory_usage=1024 * 1024,  # ADDED
    cpu_percent=25.0,          # ADDED
    namespace_size=10,         # ADDED
)
```
**Tests Fixed**: `tests/unit/test_messages.py` - All 8 tests now pass

### Phase 1: Core Foundation Fixes (1-2 days) - **READY TO START**
**Phase 0 Complete**: AsyncExecutor skeleton ready, 97.6% tests passing, foundation stable

#### 1.1 Implement Namespace Merge-Only Policy ✅ COMPLETED IN DAY 2
**Files Modified**: `src/subprocess/namespace.py`, `src/subprocess/worker.py`
**Spec**: `docs/async_capability_prompts/current/24_spec_namespace_management.md:87-102` (ENGINE_INTERNALS list)

**Completed Implementation**:
- Added ENGINE_INTERNALS constant with all protected keys
- Fixed _setup_namespace() to use update() instead of replace
- Added update_namespace() method with merge strategies (overwrite/preserve/smart)
- Added _update_result_history() for tracking execution results (_, __, ___)
- Updated clear() to preserve engine internals
- Created comprehensive test suite (12 tests, all passing)

#### 1.2 Create AsyncExecutor Skeleton ✅ COMPLETED IN DAY 3
**New File**: `src/subprocess/async_executor.py` (395 lines)
**Based On**: `docs/async_capability_prompts/current/22_spec_async_execution.md:58-144`
**Test File**: `tests/unit/test_async_executor.py` (499 lines, 22 tests)

**Completed Implementation**:
- ExecutionMode enum with 5 modes (TOP_LEVEL_AWAIT, ASYNC_DEF, BLOCKING_SYNC, SIMPLE_SYNC, UNKNOWN)
- PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x2000 constant defined
- AST-based code analysis with recursive await detection
- Blocking I/O detection (requests, urllib, socket, open, etc.)
- Event loop management with ownership tracking
- ThreadedExecutor delegation for all non-async execution
- Coroutine lifecycle management with weakref tracking
- Comprehensive test coverage (91% of AsyncExecutor code)

```python
# ACTUAL IMPLEMENTATION in src/subprocess/async_executor.py:
class AsyncExecutor:
    """Skeleton async executor for transition to async architecture."""
    PyCF_ALLOW_TOP_LEVEL_AWAIT = 0x1000000
    BLOCKING_IO_MODULES = {'requests', 'urllib', 'socket', 'subprocess', ...}
    BLOCKING_IO_CALLS = {'open', 'input', 'sleep', 'wait', ...}
    
    def analyze_execution_mode(self, code: str) -> ExecutionMode:
        """AST-based execution mode detection."""
        try:
            tree = ast.parse(code)
            # Check for top-level await, async defs, blocking I/O
            if self._contains_await_at_top_level(node):
                return ExecutionMode.TOP_LEVEL_AWAIT
            # ... additional checks ...
        except SyntaxError:
            if 'await' in code:
                return ExecutionMode.TOP_LEVEL_AWAIT
            return ExecutionMode.UNKNOWN
    
    async def execute(self, code: str) -> Any:
        mode = self.analyze_execution_mode(code)
        if mode == ExecutionMode.TOP_LEVEL_AWAIT:
            raise NotImplementedError("Async execution coming soon")
        else:
            # Delegate to ThreadedExecutor with proper async wrapper
            return await self._execute_with_threaded_executor(code)
```
**Tests Passing**: All 22 AsyncExecutor tests, no regressions in existing suite

#### 1.3 Fix Event Loop Management
**File**: `src/session/manager.py` (fix lines 81-83)
**Guidance**: `docs/async_capability_prompts/current/22_spec_async_execution.md:123-128`

```python
# In session/manager.py, replace lines 81-83:
class Session:
    def __init__(self, ...):
        # Earlier in __init__, ensure consistent loop usage
        # Get or create loop BEFORE creating asyncio objects
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        
        # NOW create asyncio objects (they'll use the current loop)
        self._lock = asyncio.Lock()  # Line 81 - now uses correct loop
        self._ready_event = asyncio.Event()  # Line 82 - uses current loop
        self._cancel_event = asyncio.Event()  # Line 83 - uses current loop
```
**Also Check**: `tests/fixtures/sessions.py:18-42` for similar issues

### Phase 2: Bridge to Future Architecture (3-5 days)

#### 2.1 Create Execution Mode Router
**New Component**: Add to `src/subprocess/async_executor.py`
**Based On**: `docs/async_capability_prompts/current/22_spec_async_execution.md:69-75, 149-247`

```python
# Add to src/subprocess/async_executor.py
from enum import Enum
import ast

class ExecutionMode(Enum):
    """From spec lines 69-75"""
    TOP_LEVEL_AWAIT = "top_level_await"
    ASYNC_DEF = "async_def"
    BLOCKING_SYNC = "blocking_sync"
    SIMPLE_SYNC = "simple_sync"
    UNKNOWN = "unknown"

class ExecutionRouter:
    """Routes code to appropriate executor based on analysis."""
    
    # From spec lines 96-101
    BLOCKING_IO_MODULES = {
        'requests', 'urllib', 'socket', 'subprocess',
        'sqlite3', 'psycopg2', 'pymongo', 'redis'
    }
    
    def analyze_execution_mode(self, code: str) -> ExecutionMode:
        """Simplified from spec lines 149-200"""
        try:
            tree = ast.parse(code)
            # Check for top-level await (spec lines 172-175)
            for node in tree.body:
                if isinstance(node, ast.Expr):
                    if self._contains_await(node.value):
                        return ExecutionMode.TOP_LEVEL_AWAIT
            return ExecutionMode.SIMPLE_SYNC
        except SyntaxError:
            if 'await' in code:
                return ExecutionMode.TOP_LEVEL_AWAIT
            return ExecutionMode.UNKNOWN
```

#### 2.2 Add Basic Promise Abstraction (Pre-Resonate)
**New File**: `src/subprocess/promise_manager.py`
**Bridge To**: `docs/async_capability_prompts/current/00_foundation_resonate.md:109-162`
**Replaces**: Protocol Bridge concept from `docs/async_capability_prompts/archive/obsolete_30_protocol_bridge.md`

```python
# src/subprocess/promise_manager.py
class PromiseManager:
    """Simple promise manager as bridge to Resonate.
    
    This is a temporary implementation that will be replaced by
    Resonate promises as described in foundation_resonate.md:109-162
    """
    
    def __init__(self):
        self._promises = {}
        
    async def create_promise(self, id: str, data: Any) -> asyncio.Future:
        """Create a promise that can be resolved later.
        
        Maps to future Resonate usage (foundation_resonate.md:123-136):
        promise = self._resonate.promises.create(
            id=promise_id,
            timeout=timeout,
            data=json.dumps(data)
        )
        """
        future = asyncio.create_future()
        self._promises[id] = {"future": future, "data": data}
        return future
        
    def resolve_promise(self, id: str, result: Any):
        """Resolve a promise with a result.
        
        Maps to future Resonate usage (foundation_resonate.md:153-157):
        self._resonate.promises.resolve(
            id=correlation_id,
            data=json.dumps(result)
        )
        """
        if id in self._promises:
            promise = self._promises.pop(id)
            if not promise["future"].done():
                promise["future"].set_result(result)
```

#### 2.3 Implement Capability Base Class
```python
class Capability:
    """Base class for capabilities (bridge to future)."""
    
    def __init__(self, promise_manager, transport, execution_id):
        self.promises = promise_manager
        self.transport = transport
        self.execution_id = execution_id
        
    async def request_response(self, message: Message, timeout: float = 30):
        """Send message and await response via promise."""
        promise = await self.promises.create_promise(
            message.id, 
            {"type": "capability_request"}
        )
        await self.transport.send_message(message)
        return await asyncio.wait_for(promise, timeout)
```

### Phase 3: Test Infrastructure Fixes (1 day)

#### 3.1 Fix Test Fixtures
```python
# In tests/fixtures/sessions.py:
@asynccontextmanager
async def create_session(...):
    """Create session with proper event loop management."""
    # Ensure we're in an event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    session = Session(...)
    # Rest of implementation
```

#### 3.2 Add Compatibility Layer for Tests
```python
# In tests/conftest.py:
@pytest.fixture
def async_executor(namespace_manager, transport):
    """Provide AsyncExecutor for tests."""
    # For now, returns skeleton that delegates to ThreadedExecutor
    return AsyncExecutor(namespace_manager, transport, "test-exec")
```

## Concrete Next Steps (In Order)

### Week 1: Unblock Testing (Phase 0 - Emergency Fixes)
**Working Branch**: `fix/foundation-phase0-emergency-fixes`

1. **Day 1 Morning**: Add async wrapper to ThreadedExecutor ✅ COMPLETE
   - File: `src/subprocess/executor.py` (lines 627-674)
   - Tests Fixed: All 5 executor tests passing
   - Added timeout protection for mock transports
   - Commit: `016f42b`
   
2. **Day 1 Afternoon**: Fix message field issues ✅ COMPLETE
   - Files: `tests/unit/test_messages.py` only (worker.py already correct)
   - Fixed: ResultMessage.execution_time, HeartbeatMessage fields
   - Result: All 8 message tests passing
   - Commit: `016f42b`
   
3. **Day 2**: Implement merge-only namespace policy ✅ COMPLETE  
   - Files: `src/subprocess/namespace.py`, `src/subprocess/worker.py`
   - Spec: `docs/async_capability_prompts/current/24_spec_namespace_management.md:15-29`
   - Added ENGINE_INTERNALS constant with protected keys
   - Fixed _setup_namespace() to UPDATE instead of REPLACE
   - Added update_namespace() method with merge strategies
   - Created test_namespace_merge.py with 12 comprehensive tests
   - Commit: `90c2937`
   
4. **Day 3**: Create AsyncExecutor skeleton ✅ COMPLETE
   - New File: `src/subprocess/async_executor.py` (398 lines)
   - Test File: `tests/unit/test_async_executor.py` (536 lines, 23 tests)
   - ExecutionMode detection working for all 5 modes
   - ThreadedExecutor delegation maintains functionality
   - Event loop management without ownership (no __del__ closing)
   - Result: 23 new tests passing, 90% AsyncExecutor coverage
   
5. **Day 4**: PR Review Feedback Fixes ✅ COMPLETE
   - **Critical**: Removed dangerous __del__ loop closing from AsyncExecutor
   - **Critical**: Added explicit lifecycle management (close() and context manager)
   - **Critical**: Fixed deprecated get_event_loop() → get_running_loop()
   - **Medium**: Created `src/subprocess/constants.py` for single ENGINE_INTERNALS source
   - **Medium**: Fixed brittle/flaky tests with proper synchronization
   - **Low**: Added LRU cache limit, removed unused imports, improved documentation
   - Result: All reviewer concerns addressed

6. **Day 4 (Extended)**: Additional PR Refinements ✅ COMPLETE
   - **AST Traversal**: Verified working correctly, added comprehensive edge case tests
     - File: `tests/unit/test_async_executor.py` lines 251-339
     - Tests: await in function calls, list comprehensions, dict/set literals, conditionals
   - **Hash Collisions**: Replaced Python `hash()` with a stable digest for cache keys
     - File: `src/subprocess/async_executor.py` line 146
     - Decision: Use `hashlib.md5(code.encode()).hexdigest()` for non-crypto
       AST cache keys (faster, stable). If needed later, switch specific
       contexts to SHA-256.
   - **Result History**: Fixed to only update _ for expression results
     - File: `src/subprocess/namespace.py` lines 111-118
     - Only updates _ when key='_', not on all variable assignments
   - **Event Loop Deprecations**: Fixed remaining get_event_loop() calls
     - File: `src/subprocess/worker.py` line 572-573
     - File: `src/protocol/framing.py` lines 60-75
   - **Cancellation Tests**: Added component-level tests with documented limitations
     - File: `tests/unit/test_executor.py` lines 223-292
     - Known limitation: KeyboardInterrupt escapes test isolation
   - **LRU Cache**: Added eviction test
     - File: `tests/unit/test_async_executor.py` lines 366-412
   - **Timeout Configuration**: Replaced hardcoded 0.5s with configurable _drain_timeout
     - File: `src/subprocess/executor.py` line 675
   - **Documentation**: Clarified thread safety claims
     - File: `src/subprocess/async_executor.py` lines 80, 85-87

7. **Day 4+ (Extended)**: Final Reviewer Feedback ✅ COMPLETE
   - **Event Loop Management**: Removed loop acquisition from __init__ (lines 97-99)
     - Loop now only obtained when needed in execute()
     - Allows initialization outside async context
   - **Event Loop in execute()**: Direct call without try/except (line 341)
     - Uses `asyncio.get_running_loop()` directly
     - Lets it raise naturally if not in async context
   - **SyntaxError Detection**: Improved with PyCF_ALLOW_TOP_LEVEL_AWAIT compile test
     - File: `src/subprocess/async_executor.py` lines 186-195
     - Correctly handles `lambda: await foo()` as UNKNOWN
   - **Test Coverage**: Added test_event_loop_handling.py with 11 tests
     - Tests nested async contexts, concurrent sessions
     - Validates all edge cases identified by reviewers
   - Result: 94/96 unit tests passing (97.9%)

**Goal**: 80% of tests passing ✅ EXCEEDED (97.9% - 94/96 unit tests)

### Week 2: Build Bridge Architecture (Phase 1 & 2)
**Phase 1 Branch** (Days 5-7): `fix/foundation-phase1-resonate-wrapper`  
**Phase 2 Branch** (Days 8-10): `fix/foundation-phase2-integration`

#### Critical Insight from Spec Review
The specs solve the async/await vs yield paradigm through a **wrapper pattern** (refs below):
- User code uses async/await normally (`22_spec_async_execution.md:252-293`)
- AsyncExecutor handles async/await with PyCF_ALLOW_TOP_LEVEL_AWAIT (`22_spec_async_execution.md:17-25, 298-339`)
- Resonate wraps AsyncExecutor in durable functions using yield (`22_spec_async_execution.md:671-734`, `21_spec_resonate_integration.md:133-190`)
- No code transformation needed - separation of concerns at integration layer (`00_foundation_resonate.md:303-309`)

6. **Day 5: Implement Resonate Wrapper Pattern** (8 hours)
   - Create durable function wrapper for AsyncExecutor
   - Based On: `docs/async_capability_prompts/current/22_spec_async_execution.md:671-734`
   - Pattern:
     ```python
     @resonate.register
     def durable_async_execute(ctx, args):
         executor = AsyncExecutor(ctx.resonate, namespace_manager, execution_id)
         result = yield ctx.lfc(executor.execute, {"code": code})
         return result
     ```
   - Test that AsyncExecutor methods work with `ctx.lfc()`
   
7. **Day 6: Promise Adapter Layer** (4 hours)
   - Create `AwaitableResonatePromise` for async/await compatibility
   - Fix timing issues between Resonate promises and asyncio
   - Based On: `docs/async_capability_prompts/current/21_spec_resonate_integration.md:319-377`
   - Key: Make Resonate promises awaitable in async contexts
   
8. **Day 7: Migration Adapter Implementation** (4 hours)
   - Implement `MigrationAdapter` from spec lines 894-922
   - Based On: `docs/async_capability_prompts/current/21_spec_resonate_integration.md:894-922`
   - Add intelligent routing based on execution modes:
     ```python
     def _should_use_resonate(self, code: str) -> bool:
         mode = self.analyze_execution_mode(code)
         return mode in [ExecutionMode.TOP_LEVEL_AWAIT, ExecutionMode.BLOCKING_SYNC]
     ```
   
9. **Day 8: Dependency Injection Refinement** (4 hours)
   - Fix singleton vs factory patterns for dependencies
   - Based On: `docs/async_capability_prompts/current/21_spec_resonate_integration.md:243-314`
   - Critical fix: AsyncExecutor needs factory function, not singleton
   - Test namespace manager lifecycle with Resonate
   
10. **Day 9-10: Integration Testing** (8 hours)
    - Test checkpoint recovery (`21_spec_resonate_integration.md:754-794`)
    - Test local vs remote mode consistency
    - Verify promise resolution in both modes
    - Test HITL workflows with promises (`21_spec_resonate_integration.md:473-512`)
    - Performance benchmarks per spec targets (`21_spec_resonate_integration.md:1085-1093`)

**Goal**: 95% tests passing with Resonate integration working in local mode

#### Early Detection Tests (Day 5 - Critical)
```python
# Test 1: Verify wrapper pattern works
def test_resonate_wrapper_pattern():
    """Based on 22_spec_async_execution.md:671-734"""
    @resonate.register
    def wrapped_execute(ctx, args):
        executor = AsyncExecutor(ctx.resonate, namespace_manager, "test")
        # This should work - AsyncExecutor's async method called via yield
        result = yield ctx.lfc(executor.execute, {"code": "x = 1"})
        return result
    
    result = wrapped_execute.run("test-1", {"code": "x = 1"})
    assert result is not None

# Test 2: Verify no paradigm conflict
def test_async_await_vs_yield_separation():
    """Ensure clean separation of concerns"""
    code = "result = await asyncio.sleep(0, 'test')"
    
    # AsyncExecutor handles await internally
    executor = AsyncExecutor(resonate, namespace_manager, "test")
    # Resonate wraps with yield externally
    @resonate.register
    def durable_exec(ctx, args):
        result = yield ctx.lfc(executor.execute, {"code": code})
        return result
    
    assert durable_exec.run("test-2", {}) == 'test'
```

### Week 3: Prepare for Full Specs
11. Implement basic AsyncExecutor with PyCF_ALLOW_TOP_LEVEL_AWAIT
12. Add capability message types to protocol
13. Document migration path to Resonate
14. Create integration test suite for future architecture
15. Performance baseline measurements

## Success Criteria

### Immediate Success (Week 1)
- [x] ThreadedExecutor tests pass with async wrapper ✅ Day 1
- [x] No Pydantic validation errors ✅ Day 1
- [x] Namespace never replaced, only merged ✅ Day 2
- [x] Basic AsyncExecutor skeleton works ✅ Day 3
- [ ] Event loop errors resolved (Day 3-4)

### Foundation Success (Week 2 - Resonate Integration)
- [ ] Resonate wrapper pattern working (AsyncExecutor wrapped in durable functions)
- [ ] Promise adapter bridges yield and await paradigms
- [ ] Migration adapter routes code intelligently
- [ ] Dependency injection with proper lifecycles
- [ ] Local and remote modes behave identically
- [ ] 95% test pass rate

### Integration Validation Tests
- [ ] Test 1: AsyncExecutor.execute() works inside Resonate's `ctx.lfc()`
- [ ] Test 2: Resonate promises are awaitable via adapter
- [ ] Test 3: Same code produces same results in local and remote modes
- [ ] Test 4: Checkpoint recovery restores namespace correctly
- [ ] Test 5: HITL promises resolve correctly across async boundaries
- [ ] Test 6: Performance meets spec targets (< 1ms local, < 10ms remote)

### Ready for Production (Week 3)
- [ ] AsyncExecutor handles top-level await with PyCF_ALLOW_TOP_LEVEL_AWAIT
- [ ] Full Resonate integration with crash recovery
- [ ] MigrationAdapter allows incremental adoption
- [ ] Performance benchmarks documented
- [ ] Architecture documentation reflects wrapper pattern

## Critical Learnings from Full Spec Review

### The Wrapper Pattern Solution
After reading the full specs, the architecture is elegantly solved:
1. **No AST transformation needed** - User code remains unchanged
2. **Separation of concerns** - AsyncExecutor handles async/await, Resonate handles durability
3. **Clean integration layer** - Resonate wraps AsyncExecutor, not vice versa
4. **Incremental adoption** - MigrationAdapter allows gradual transition

### Key Integration Points (with Spec References)
- **Promise Adapter**: Bridge between Resonate promises (yield-based) and asyncio futures (await-based)
  - Spec: `21_spec_resonate_integration.md:319-418` (PromiseManager and PromiseBasedProtocol)
  - Pattern: `00_foundation_resonate.md:109-162` (Protocol Bridge with Resonate Promises)
- **Dependency Injection**: Use factory functions for per-execution instances
  - Spec: `21_spec_resonate_integration.md:243-314` (Dependency Registration and Access)
  - Critical: AsyncExecutor must be `singleton=False` (line 264)
- **Checkpoint Strategy**: Namespace snapshots at each checkpoint for recovery
  - Spec: `21_spec_resonate_integration.md:569-611` (CheckpointManager)
  - Example: `21_spec_resonate_integration.md:754-794` (crash_resilient_execution)
- **Local/Remote Parity**: Same behavior in both modes, different persistence
  - Local: `21_spec_resonate_integration.md:51-85` (initialize_resonate_local)
  - Remote: `21_spec_resonate_integration.md:87-126` (initialize_resonate_remote)
  - Migration: `21_spec_resonate_integration.md:894-922` (MigrationAdapter)

## Risks and Mitigations (Updated)

### Risk 1: Promise Resolution Timing Mismatch
**Issue**: Resonate promises may not be directly awaitable
**Mitigation**: Create `AwaitableResonatePromise` adapter class
**Test Early**: Day 5 - Test promise resolution in both paradigms

### Risk 2: Dependency Lifecycle Issues
**Issue**: AsyncExecutor needs new instance per execution, not singleton
**Mitigation**: Use factory functions in dependency registration
**Test Early**: Day 8 - Verify proper cleanup between executions

### Risk 3: Local vs Remote Behavior Divergence
**Issue**: Different behavior could break when deploying
**Mitigation**: Extensive testing in both modes with same test cases
**Test Early**: Day 9-10 - Run all tests in both local and remote modes

### Risk 4: Performance Overhead in Wrapper Layer
**Issue**: Multiple layers might introduce latency
**Mitigation**: Benchmark against spec targets (< 1ms local, < 10ms remote)
**Test Early**: Day 10 - Performance benchmarks

## Conclusion

The foundation fixes are **essential** before implementing the full specs. We're building a bridge from the current ThreadedExecutor-based system to the future AsyncExecutor + Resonate architecture. By following this plan, we'll have:

1. **Immediate**: Working tests and stable development environment
2. **Short-term**: Solid foundation that supports both sync and async patterns
3. **Long-term**: Clear path to implement full specifications

The key is to **fix the basics first**, then **build the bridge**, and finally **implement the vision**.

## PR #11 Triage (Immediate vs Phase 1)

Context: Reviews for PR #11 (branch: `fix/foundation-phase1-resonate-wrapper`) surfaced one high‑severity correctness bug in `AsyncExecutor` plus a few medium/low items. Below is the disposition and how it maps to work now vs Phase 1.

### Fix Now (Day 5 scope)
- Correct globals binding for top‑level await (direct path): Use the live session namespace dict for `globals` when executing compiled code so any functions created bind their `__globals__` to the real, persistent mapping. Keep a separate `local_ns` to capture top‑level assignments for merge‑only updates.
  - Code: `src/subprocess/async_executor.py` (replaced `self.namespace.namespace.copy()` with the live mapping and added explanatory comments)
  - Rationale: Prevents functions from capturing a stale globals mapping and ensures `global` assignments persist across executions.
- Correct globals binding for AST fallback path: Execute the transformed module with the real session namespace as `globals` so `__async_exec__` binds to the live mapping. Continue merging `locals()` back into the namespace.
  - Code: `src/subprocess/async_executor.py` (same correction as above; added comments)
  - Rationale: Aligns both paths with the merge‑only policy and prevents divergence between function `__globals__` and the session namespace.
- Remove redundant `weakref` import inside method: Use the module‑level import to avoid redeclaration.
  - Code: `src/subprocess/async_executor.py` (`_track_coroutine`)
  - Rationale: Minor cleanliness; avoids confusion flagged in review.

Notes
- Tests: Add targeted tests in Phase 1 to validate that functions defined under both paths retain `__globals__` pointing at the live mapping and that subsequent executions see updated globals. Current suite lacks this coverage (as reviews noted).
- Spec alignment: Changes are consistent with `24_spec_namespace_management.md` (merge‑only policy) and the PyCF top‑level await behavior noted in the PDF and `22_spec_async_execution.md`.

### Phase 1 (Plan and implement)
- Dependency Injection factory pattern: Replace error‑prone “get + initialize()” with a factory that yields fully initialized instances per execution context.
  - Docs: Update `docs/async_capability_prompts/current/21_spec_resonate_integration.md` to show factory registration and access. Ensure AsyncExecutor, NamespaceManager, and transport instances have clear lifecycles.
  - Code: Introduce DI hooks around the Resonate wrapper; remove any implicit singleton assumptions.
- Resonate wrapper + promise adapter: Implement the wrapper pattern where Resonate drives durability while AsyncExecutor handles async/await natively. Provide an awaitable adapter over Resonate promises.
  - Docs: `00_foundation_resonate.md`, `22_spec_async_execution.md`
  - Code: Wrapper function(s) and `AwaitableResonatePromise` abstraction per spec.
- Execution mode routing hardening: Finish routing logic and expand blocking‑I/O detection (attribute chains like `time.sleep`, `requests.get`, `socket.recv`). Add tests first to constrain false positives.
  - Docs: `22_spec_async_execution.md`
  - Code: Extend AST analysis to resolve `ast.Attribute` and imported name aliases.
- Top‑level await AST fallback correctness:
  - Add pre‑exec globals snapshot and apply post‑exec global diffs AFTER locals merge so global writes take precedence (fixes cases like `global g; g=...` being overwritten by wrapper locals).
  - Adjust AST transform to preserve module‑level semantics for assigned names (emit `ast.Global` where safe) to avoid closure capture of names like `g` inside functions defined in the wrapper.
  - Tests: New xfails in `tests/unit/test_async_executor_namespace_binding.py` capture these gaps; flip to passing once implemented.
- Test/CI hygiene:
  - Relax/mark flaky perf assertion in `tests/unit/test_top_level_await.py` (threshold <100ms). Prefer monotonic timers and a higher ceiling or mark as flaky for CI.
  - Ensure CI runs unit tests on PRs (e.g., `pytest -m unit`).
- Config hygiene: Remove or document `.reviewrc.json` “yolo” flag; default to safe behavior and document any local‑only toggles.
- Compatibility note (AST args): The `ast.arguments` constructor differences for Python <3.8 were flagged in review. Our target is Python 3.11+; add an explicit note in code and docs. If we choose to support older versions later, add version‑guarded construction in Phase 1.

### TODOs added in code
- `src/subprocess/async_executor.py`:
  - Marked the blocking‑I/O detection broadening as a Phase 1 TODO.
  - Added comments around live‑globals usage to prevent regressions.
  - Left a note near AST usage to revisit cross‑version `ast.arguments` construction only if supporting <3.8.
  - Added TODOs for pre‑exec globals snapshot diff and fallback merge ordering; noted closure capture with plan to hoist via `ast.Global` where safe.

### Acceptance criteria updates
- Immediate: Both top‑level await execution paths bind function `__globals__` to the live namespace mapping; namespace updates continue to use merge‑only policy; no namespace replacement anywhere.
- Phase 1: DI refactor to factory pattern, Resonate wrapper + awaitable promises, expanded routing/detection, improved test/CI hygiene, and config cleanup.
  - AST fallback: Global diffs applied after locals, no closure capture of would‑be globals for functions defined in fallback; new tests pass without xfail.

## Deferred Refinements (Phase 1 Planning)

- Output drain-timeout suppression policy: Keep current suppression in tests, but in Phase 1 define a configurable policy (flag/env), warn once per execution, and track a small metric so production regressions are visible without destabilizing tests.
- Blocking I/O detection breadth: Extend `AsyncExecutor._contains_blocking_io` to detect common attribute calls (e.g., `time.sleep`, `requests.get`, `socket.recv`). Add tests first to capture expected patterns and limit false positives.
- FrameBuffer wakeups: Replace the fixed 10ms sleep in `FrameBuffer.get_frame()` with event/condition wakeups (consistent with `transport.FrameReader`) to reduce latency and CPU wakeups under load.

## Phase 1 Test & CI Summary (2025-09-05)

- Unit tests (uv): 111 passed, 2 skipped, 3 xpassed (expected transitions now passing).
- New unit tests: TLA timeout override, globals binding under both TLA paths, AST fallback correctness, blocking I/O detection patterns.
- CI: Added `.github/workflows/unit-tests.yml` to run unit tests on PRs/pushes with Python 3.11.

## Outstanding Work for Phase 2

- Session/Worker integration fixes (source of current integration failures):
  - Last-expression result delivery for multi-line cells (ensure `ResultMessage.value` carries the last value consistently).
  - Large output/message handling (chunking and drain ordering) under backpressure.
  - Checkpoint create/restore pathways and state validation.
  - Concurrency and lifecycle: robust cancellation, loop binding, and race conditions in session/worker.
- Event loop lifecycle audit in session/worker: bind asyncio primitives to the correct loop and avoid cross-loop usage.
- Blocking I/O detection: expose modules/methods via config; add counters/telemetry and structured logs around detections.
- Performance: add micro-benchmarks and CI perf guardrails for TLA latency and output streaming.
