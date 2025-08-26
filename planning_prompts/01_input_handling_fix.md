# Input Handling Fix Planning Prompt

## Your Mission

You are tasked with planning the fix for PyREPL3's broken input() functionality that causes EOFError when any code attempts to read user input, while preserving the single-reader architecture that prevents deadlocks.

## Context

### Historical Context (Problem Archaeology)

#### Previous Attempts and Failures
1. **v0 Dual-Reader Architecture**
   - What: Main thread + control thread both reading stdin
   - Why Failed: Race conditions and deadlocks after streaming operations
   - Lesson: File descriptors are single-consumer resources; two readers on stdin causes message consumption by wrong reader

2. **v0.1 Single-Reader Fix**
   - What: Eliminated control thread, single background _read_loop
   - Success: Fixed deadlock completely
   - Trade-off: stdin exclusively owned by protocol, unavailable for user input()

3. **exec-py v0.1.1 Input Solution**
   - What: Override builtin input with protocol-aware version
   - Success: One-line fix enabled full input support
   - Key Insight: Infrastructure was complete, just not connected

#### Discovered Invariants
- **Single-Reader Invariant**: Only one component can read from stdin without race conditions
- **Protocol Ownership**: stdin belongs exclusively to Frame protocol for Manager↔Worker communication
- **Namespace Isolation**: Each execution has isolated namespace where builtins can be overridden

### Existing Infrastructure (Architecture Recognition)

#### Working Components
- **InputHandler class** (src/subprocess/worker.py:140-191)
  - Already implements request_input() method
  - Sends INPUT_REQUEST message via transport
  - Waits for INPUT_RESPONSE with token correlation
  - Handles timeout correctly

- **Protocol Messages** (src/protocol/messages.py)
  - InputMessage: Requests input with prompt
  - InputResponseMessage: Provides user data
  - Token-based correlation already implemented

- **Message Routing** (src/session/manager.py)
  - _receive_loop routes messages by type
  - Can handle INPUT_REQUEST and route responses

#### Leverage Points
```python
# Current flow (broken):
user_code: input("prompt") → builtin input → reads stdin → EOFError (stdin owned by protocol)

# Fixed flow (to implement):
user_code: input("prompt") → overridden input → InputHandler → INPUT_REQUEST message → protocol
```

#### Gap Analysis
- InputHandler exists: ✅
- Protocol messages defined: ✅
- Message routing works: ✅
- **Missing**: Connection between builtin input() and InputHandler ❌

## Constraints

### Non-Negotiable Requirements
1. **Single-Reader Invariant**: Must not create additional stdin readers (would cause deadlock)
2. **No New Threads**: Must not spawn threads for input handling (breaks architecture)
3. **Backward Compatibility**: All 29 existing tests must continue passing
4. **Protocol Integrity**: Frame-based protocol communication must remain undisturbed

### Risks to Avoid

#### Risk 1: Breaking Single-Reader Architecture
- **Probability**: High if careless
- **Impact**: Critical (deadlock returns)
- **Scenario**: Adding new stdin reader → Two readers compete → Messages consumed wrongly → Deadlock
- **Mitigation**: Override input() to use existing protocol, never touch stdin directly

#### Risk 2: Synchronous/Async Mismatch
- **Probability**: Medium
- **Impact**: Major (execution fails)
- **Scenario**: input() is synchronous, InputHandler.request_input() is async
- **Mitigation**: Bridge sync→async carefully in worker namespace

#### Risk 3: Execution Context Loss
- **Probability**: Low
- **Impact**: Major (wrong session receives input)
- **Scenario**: Input request doesn't track execution_id properly
- **Mitigation**: Pass execution_id to InputHandler for proper correlation

## Planning Approach

### Solution Space Analysis

#### Approach A: Namespace Override (Recommended)
**Philosophy**: Override input in execution namespace to use protocol
**Implementation**:
```python
# In SubprocessWorker._setup_namespace() around line 227:
self._namespace["input"] = self._create_protocol_input()
self._namespace["__builtins__"]["input"] = self._create_protocol_input()
```
**Pros**: 
- Minimal change (5-10 lines)
- Uses existing infrastructure
- Subprocess isolation makes override safe
**Cons**: 
- Global state modification (acceptable in subprocess)
**Best When**: Always (this is the proven approach)

#### Approach B: Direct Builtin Override
**Philosophy**: Replace builtins.input globally in worker
**Implementation**:
```python
import builtins
builtins.input = protocol_aware_input
```
**Pros**: Works for all code including imports
**Cons**: More invasive than necessary

#### Approach C: AST Transformation (Not Recommended)
**Philosophy**: Transform input() calls during code parsing
**Pros**: No runtime override needed
**Cons**: Complex, fragile, breaks dynamic code

### Calibration
<context_gathering>
Search depth: Low (solution is clear from exec-py precedent)
Tool budget: 5-10 (verify existing code, implement fix, test)
Early stop: When input() works without EOFError
</context_gathering>

## Implementation Guide

### Phase 1: Verification (20% effort)
1. Confirm InputHandler exists and works (src/subprocess/worker.py:140)
2. Verify protocol messages are defined (src/protocol/messages.py:62-75)
3. Run test_reproductions/test_input_broken.py to baseline failure

### Phase 2: Core Changes (60% effort)

#### File: src/subprocess/worker.py

**Change 1**: Add execution_id tracking (line ~194)
```python
class SubprocessWorker:
    def __init__(self, transport: MessageTransport, session_id: str) -> None:
        # ... existing code ...
        self._current_execution_id: Optional[str] = None  # ADD THIS
```

**Change 2**: Create protocol input function (new method ~line 230)
```python
def _create_protocol_input(self) -> callable:
    """Create input() replacement that uses protocol."""
    
    def protocol_input(prompt: str = "") -> str:
        """Synchronous wrapper for async input handling."""
        import asyncio
        
        # Get or create event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Create async input handler
        handler = InputHandler(self._transport, self._current_execution_id)
        
        # Run async operation synchronously
        future = asyncio.ensure_future(handler.request_input(prompt))
        return loop.run_until_complete(future)
    
    return protocol_input
```

**Change 3**: Override input in namespace (line ~227 in _setup_namespace)
```python
def _setup_namespace(self) -> None:
    """Setup the initial namespace."""
    import builtins
    
    # Start with clean namespace
    self._namespace = {
        "__name__": "__main__",
        "__doc__": None,
        "__package__": None,
        "__loader__": None,
        "__spec__": None,
        "__annotations__": {},
        "__builtins__": builtins,
    }
    
    # Override input() to use protocol
    protocol_input = self._create_protocol_input()
    self._namespace["input"] = protocol_input
    builtins.input = protocol_input  # Also override globally for imported code
```

**Change 4**: Track execution_id (line ~281 in execute method)
```python
async def execute(self, message: ExecuteMessage) -> None:
    """Execute Python code."""
    execution_id = message.id
    self._current_execution_id = execution_id  # ADD THIS
    # ... rest of method ...
```

### Phase 3: Validation (20% effort)

1. Update test_reproductions/test_input_broken.py to handle input responses
2. Run all tests to ensure no regression
3. Test multiple inputs, inputs in functions, concurrent inputs

## Output Requirements

Your planning deliverable must include:

1. **Approach Selection**: Namespace Override approach with clear rationale
2. **Implementation Steps**: 
   - Exact file locations and line numbers
   - Complete code snippets (not pseudo-code)
   - Order of changes to avoid intermediate breaks
3. **Risk Mitigation**: 
   - How single-reader invariant is preserved
   - How sync/async bridge works safely
4. **Test Strategy**:
   - Modify test_input_broken.py to send input responses
   - Test cases: single input, multiple inputs, input in functions
5. **Success Criteria**:
   - input("prompt") returns user value without EOFError
   - All existing tests still pass
   - No thread count increase
   - No deadlocks after implementation

## Success Validation

### Functional Tests
| Requirement | Test Case | Expected Result | Pass Criteria |
|------------|-----------|-----------------|---------------|
| Basic input works | `name = input("Name: ")` | Returns "Alice" | No EOFError |
| Multiple inputs | Two sequential input() calls | Both return values | Both succeed |
| Input in function | Function containing input() | Returns value | No error |
| Existing tests pass | Run full test suite | All pass | 100% pass rate |

### Technical Validation
- Thread count remains at 2 (MainThread + asyncio-waitpid)
- No new stdin readers created
- Protocol messages properly correlated by token
- Execution context preserved (correct session receives input)

### Test Implementation
```python
# Modified test that handles input
async def test_with_input_response():
    session = Session()
    await session.start()
    
    code = 'name = input("Name: "); print(f"Hello {name}")'
    msg = ExecuteMessage(id="test", timestamp=0, code=code)
    
    # Start execution (don't await)
    exec_task = asyncio.create_task(session.execute(msg))
    
    # Wait for input request
    # Send input response
    # Verify output contains "Hello Alice"
```

## Expected Outcome

After implementing this plan:
1. ✅ input() will work correctly in all executed code
2. ✅ Interactive programs can request and receive user input
3. ✅ No regression in existing functionality
4. ✅ Architecture remains clean with single-reader invariant intact
5. ✅ Solution is minimal (~20 lines of code changed)