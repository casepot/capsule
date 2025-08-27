# Unresolved Issues and Areas for Investigation

## Critical Issues Requiring Immediate Attention

### 1. ResultMessage Value Serialization
**Status**: 🔴 Blocking multiple tests  
**Impact**: Results often have `value=None` when they shouldn't

**Symptoms**:
- `ResultMessage.value` is None even for simple expressions
- `repr` field is empty string
- Affects both unit and integration tests

**Investigation Needed**:
- Check msgpack serialization of Python objects
- Verify namespace `_` (underscore) handling
- Test serialization of complex types (tuples, dicts, classes)

**Affected Tests**:
- `test_messages.py::test_result_message_creation`
- `test_worker_communication.py` - multiple result assertions
- `test_core_execution.py::test_last_result_underscore`

### 2. Worker Restart After Crash
**Status**: 🔴 Critical for reliability  
**Impact**: Session cannot recover from worker crashes

**Symptoms**:
```python
asyncio.exceptions.CancelledError: Session cancelled/terminating
# During restart attempt at src/session/manager.py:281
```

**Root Cause Hypothesis**:
- Cancel event not cleared before restart
- Message handlers not cleaned up
- Transport not properly reinitialized

**Investigation Needed**:
- Trace cancel event lifecycle
- Check transport cleanup on terminate
- Verify process cleanup before restart

### 3. Checkpoint/Restore Protocol
**Status**: 🟡 Feature incomplete  
**Impact**: State persistence not working

**Issues**:
- `CheckpointMessage` and `RestoreMessage` not fully handled
- No actual checkpoint creation in worker
- Protocol expects different response messages than implemented

**Investigation Needed**:
- Complete checkpoint handler in worker
- Implement actual dill serialization
- Add checkpoint storage mechanism

## Medium Priority Issues

### 4. Large Message Handling
**Status**: 🟡 Performance issue  
**Impact**: Large outputs may fail or timeout

**Symptoms**:
- Tests with 100KB+ output failing
- Possible frame size limits hit

**Investigation Needed**:
- Check max frame size limits (currently 10MB)
- Test streaming/chunking for large data
- Verify msgpack size limits

### 5. Executor Output Capture
**Status**: 🟡 Test infrastructure issue  
**Impact**: 4 unit tests failing

**Issues**:
- Mock configuration for ThreadSafeOutput
- Async output pump not properly tested
- Cancellation mechanism tests failing

**Investigation Needed**:
- Review ThreadedExecutor output capture
- Fix mock setup for output streams
- Verify cancellation token propagation

## Low Priority Issues

### 6. Message to_dict Conversion
**Status**: 🟢 Minor issue  
**Impact**: 2 unit tests failing

**Issue**: Message serialization tests expect different format

**Investigation Needed**:
- Check Pydantic model_dump() vs custom to_dict()
- Verify field inclusion/exclusion rules

## Architectural Gaps

### 7. Session Pool Coverage (12%)
**Not Investigated** - Entire subsystem barely tested

**Missing Tests**:
- Pool warmup mechanism
- Concurrent session acquisition
- Dead session cleanup
- Session allocation strategies
- Metrics collection

### 8. Namespace Management (15% coverage)
**Not Investigated** - Core functionality untested

**Missing Tests**:
- Function source extraction
- Import tracking
- Global state management
- Safe execution context

## Unexplained Behaviors

### 9. Heartbeat Message Internals
**Observation**: Heartbeats sent but not exposed via execute()

**Questions**:
- Should heartbeats be yielded to client?
- How to handle heartbeat during long execution?
- Timeout reset on heartbeat?

### 10. Input Timeout Configuration
**Issue**: Hardcoded timeouts in ThreadedExecutor

**Current Values**:
- `input_send_timeout`: 5.0 seconds
- `input_wait_timeout`: 300.0 seconds

**Needed**:
- Make configurable via SessionConfig
- Add to worker initialization
- Document timeout behavior

## Testing Infrastructure Gaps

### 11. Missing Test Fixtures
**Needed Fixtures**:
- Shared session pool
- Mock worker process
- Protocol message builders
- Async test utilities

### 12. Integration Test Helpers
**Needed Helpers**:
- Execute with automatic input handling
- Message collection utilities
- Timeout management
- State verification helpers

## Documentation Gaps

### 13. Protocol Specification
**Missing Documentation**:
- Complete message flow diagrams
- State transition charts
- Error handling protocols
- Timeout and retry policies

### 14. Architecture Documentation
**Needs Update**:
- How ThreadedExecutor actually works
- Protocol bridging explanation
- Session lifecycle details
- Worker subprocess management

## Performance Concerns

### 15. Session Creation Overhead
**Not Measured**:
- Time to create new session
- Memory per session
- Process creation cost
- Warmup effectiveness

### 16. Message Throughput
**Not Benchmarked**:
- Messages per second capacity
- Frame size optimization
- Serialization overhead
- Network vs pipe transport

## Next Steps Priority Order

1. **Fix ResultMessage serialization** - Blocks most important tests
2. **Fix worker restart** - Critical for reliability
3. **Complete checkpoint protocol** - Key feature
4. **Add session pool tests** - Major gap in coverage
5. **Document protocol fully** - Needed for maintenance

## Investigation Techniques That Worked

### Successful Approaches
- Reading investigation_log.json for historical context
- Comparing test expectations with actual source
- Adding debug prints to trace message flow
- Using pytest -xvs for detailed failure analysis

### Useful Patterns Found
- Session reuse is mandatory (not optional)
- Background tasks need explicit start/stop
- Protocol messages need all fields
- Mock configuration must match sync/async signatures

## Questions for Design Review

1. Why is ResultMessage.value serialization failing?
2. Should cancel events propagate to restarted workers?
3. Is checkpoint/restore a critical feature?
4. What's the intended session pool size limit?
5. Should heartbeats reset execution timeouts?

## Tools and Commands for Further Investigation

```bash
# Check specific test failure
uv run pytest tests/path/to/test.py::TestClass::test_method -xvs

# Get coverage for specific module
uv run pytest tests/ --cov=src.module --cov-report=term-missing

# Trace message flow
PYTHONPATH=. python3 -c "from src.session.manager import Session; ..."

# Check investigation history
python3 -c "import json; data=json.load(open('docs/investigations/troubleshooting/investigation_log.json')); [print(f\"{e['timestamp']}: {e['summary']}\") for e in data[-10:]]"
```

## Conclusion

While significant progress was made (76% pass rate achieved), several architectural issues remain unresolved. The most critical are ResultMessage serialization and worker restart failures. The checkpoint system appears incomplete by design, and the session pool lacks comprehensive testing.

The investigation revealed that many "broken" tests were actually testing non-existent APIs, highlighting the importance of verifying implementations before writing tests. Future work should focus on the serialization issue first, as it blocks the most tests and represents core functionality.