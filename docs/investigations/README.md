# PyREPL3 Investigations

This directory contains detailed investigations, analyses, and troubleshooting reports for the PyREPL3 project.

## Investigation Log

The main investigation log is maintained at [`troubleshooting/investigation_log.json`](troubleshooting/investigation_log.json) with 126+ detailed entries tracking bugs, fixes, and architectural discoveries.

## Current Status (August 2025)

### Test Suite Health
- **Overall Pass Rate**: 76% (improved from 64%)
- **Code Coverage**: 37% (improved from 16%)
- **Critical Systems**: Transport ✅ | Input ✅ | Worker ⚠️

### Recent Investigations

#### [Test Suite Analysis](TEST_SUITE_ANALYSIS.md)
Comprehensive analysis of test failures and fixes applied. Key findings:
- Tests were written for imaginary APIs
- Transport layer AsyncMock configuration fixed
- Input handling protocol properly integrated
- Worker lifecycle partially repaired

#### [Unresolved Issues](UNRESOLVED_ISSUES.md)
Detailed documentation of remaining problems:
- ResultMessage serialization failures
- Worker restart after crash
- Checkpoint/restore protocol incomplete
- Session pool lacking coverage

## Historical Investigations

### Transport & Communication
- [Transport Investigation](TRANSPORT_INVESTIGATION_REPORT.md) - Worker communication issues
- [Concurrent Sessions Deadlock](CONCURRENT_SESSIONS_DEADLOCK_FIX.md) - Message handler race condition
- [Async Timeout Investigation](ASYNC_TIMEOUT_INVESTIGATION_REPORT.md) - Event-driven patterns

### Architecture Deep Dives
- [v0.1 Deadlock Analysis](troubleshooting/v0.1_deadlock_analysis.md) - Historical deadlock issues

## Key Discoveries

### What's Working
✅ **ThreadedExecutor** - Input handling in threads  
✅ **Protocol Layer** - Frame-based messaging  
✅ **Event-Driven Patterns** - No polling, pure events  
✅ **Basic Worker Management** - Start/stop/execute

### What Needs Work
❌ **ResultMessage Serialization** - Values becoming None  
❌ **Worker Crash Recovery** - CancelledError on restart  
⚠️ **Checkpoint System** - Partially implemented  
⚠️ **Session Pool** - 12% test coverage

## Investigation Methodology

### Successful Techniques
1. **Historical Analysis** - Check investigation_log.json for past issues
2. **API Verification** - Compare tests with actual implementation
3. **Protocol Tracing** - Add debug logging to message flow
4. **Incremental Fixing** - Fix one subsystem at a time

### Lessons Learned
- Session reuse is mandatory (creating new Sessions exhausts resources)
- Background tasks need explicit start/stop in tests
- Protocol messages need all required fields
- Mock configuration must match async/sync signatures

## Quick Commands

```bash
# Run specific test with details
uv run pytest tests/path/to/test.py::TestClass::test_method -xvs

# Check test coverage
uv run pytest tests/ --cov=src --cov-report=term-missing

# View recent investigations
python3 -c "import json; data=json.load(open('docs/investigations/troubleshooting/investigation_log.json')); [print(f\"{e['timestamp']}: {e['summary']}\") for e in data[-5:]]"

# Check test status
uv run pytest tests/ -q --tb=no | tail -5
```

## File Organization

```
investigations/
├── README.md                          # This file
├── TEST_SUITE_ANALYSIS.md            # Comprehensive test analysis
├── UNRESOLVED_ISSUES.md              # Remaining problems
├── TRANSPORT_INVESTIGATION_REPORT.md  # Transport layer analysis
├── CONCURRENT_SESSIONS_DEADLOCK_FIX.md # Deadlock resolution
├── ASYNC_TIMEOUT_INVESTIGATION_REPORT.md # Event patterns
└── troubleshooting/
    ├── investigation_log.json         # Main investigation log (126+ entries)
    └── v0.1_deadlock_analysis.md     # Historical analysis
```

## Next Steps

1. **Fix ResultMessage serialization** (blocks many tests)
2. **Repair worker restart mechanism** (reliability issue)
3. **Complete checkpoint protocol** (feature gap)
4. **Improve session pool coverage** (12% → 70% target)
5. **Document protocol specification** (maintenance need)

## Contributing

When investigating issues:
1. Add entries to `investigation_log.json` with proper tags
2. Create detailed reports for complex investigations
3. Update this README with status changes
4. Follow the investigation methodology above