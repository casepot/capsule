# PyREPL3 Development Roadmap

## Project Vision

PyREPL3 intends to evolve beyond traditional REPL limitations to implement a **Subprocess-Isolated Execution Service (SIES)** - a managed stateful process pool with protocol-based IPC. This positions PyREPL3 as execution infrastructure rather than just an interactive shell, enabling:

- **Session-Oriented RPC** instead of stateless request/response
- **Multi-language support** through language-agnostic protocol
- **Production deployment** with resource management and monitoring
- **Network-native operation** via WebSocket/REST APIs

## Current State (v0.3.0-alpha)

PyREPL3 has successfully implemented a thread-based execution model that enables rich interactive code execution:

### ✅ Input Handling (COMPLETED)
**Implementation**: Thread-based execution model following exec-py pattern
- User code runs in dedicated threads where blocking operations are natural
- Protocol-based INPUT/INPUT_RESPONSE messages bridge thread-to-async communication  
- ThreadedExecutor class (`src/subprocess/executor.py`) manages thread lifecycle
- Non-blocking execution via `asyncio.create_task` prevents message loop deadlock
- Full support for input(), multiple sequential inputs, and input in functions

**Technical Details**:
- `ThreadSafeOutput` class redirects stdout/stderr from thread to async transport
- `create_protocol_input()` creates thread-safe input function using `asyncio.run_coroutine_threadsafe`
- Threading events coordinate between sync thread code and async message handlers
- Preserves single-reader invariant preventing stdin race conditions

### ❌ Remaining Issues
- **Session pool deadlocks** on the third concurrent acquisition
- **No API layer exists** for network access

## Near-term Baseline (v0.3.0)

With input handling complete, the remaining implementations will establish:
- Fixed pool concurrency without deadlocks
- Basic WebSocket and REST API for network access

This will establish the **Minimum Viable Product** with full interactive capabilities.

## Phase 1: Core Feature Completion (Q1 2025)

The unified planning document specified several features that exist only as message types or stubs. These must be implemented to fulfill the original vision.

### 1.1 Async Code Execution Support
**Current State**: Standard exec() model supports async function definitions and asyncio.run()

**Planned Enhancement**: Top-level await support
- AST analysis to detect await/async constructs
- Automatic wrapping in async context when needed
- Reuse worker event loop instead of creating new ones
- Would distinguish PyREPL3 from IPython's heuristic approach

**Implementation Path**:
- Detect async code via AST walk
- Choose execution path: thread for sync, event loop for async
- Maintain namespace compatibility between both modes

### 1.2 Transaction Support
**Current State**: TransactionPolicy enum exists, messages support transaction_id, but no actual implementation

**Implementation Path**:
- Implement the TransactionContext class as specified in unified plan (lines 349-366)
- Add namespace snapshotting with copy.deepcopy
- Wire transaction_policy parameter through execution flow
- Handle rollback on exceptions

**Key Decisions**:
- Memory limits for snapshot size (prevent OOM on large namespaces)
- Snapshot compression for large states
- Transaction nesting policy (disallow initially)

**Unknowns**:
- Performance impact with scientific computing libraries (numpy arrays, pandas DataFrames)
- Interaction with external resources (files, network connections)

### 1.2 Checkpoint/Restore System
**Current State**: CheckpointMessage and RestoreMessage defined but handlers are empty stubs

**Implementation Path**:
- Implement multi-tier serialization exactly as specified (lines 303-338 of unified plan)
- Complete the create_checkpoint() method with cloudpickle → msgpack → JSON fallback
- Add checkpoint storage layer (start with filesystem)
- Implement restore with namespace reconstruction

**Key Decisions**:
- Storage location (configurable path vs. fixed)
- Checkpoint lifecycle (auto-cleanup, versioning)
- Compression threshold (plan specifies 1MB)

**Unknowns**:
- Compatibility across Python versions
- Handling of active resources (threads, file handles)
- Integration with transaction snapshots (shared mechanism?)

### 1.3 FD Separation
**Current State**: Not implemented - protocol uses stdin/stdout directly

**Background**: exec-py implemented FD separation successfully, avoiding stdin conflicts

**Implementation Path**:
- Create dedicated pipe pairs for protocol communication
- Pass FD numbers via PYREPL_PROTOCOL_FDS environment variable
- Preserve exact FD numbers with pass_fds
- Add compatibility flag for environments without FD passing

**Key Decisions**:
- Default behavior (opt-in vs. opt-out)
- Windows support strategy (named pipes?)
- Fallback mechanism robustness

**Unknowns**:
- Container environment compatibility
- Performance difference vs. current approach
- Impact on debugging/logging

## Phase 2: Production Hardening (Q2 2025)

The unified plan specified performance targets and resource limits that aren't yet enforced.

### 2.1 Resource Management
**Specified Limits** (from unified plan lines 391-399):
- Memory: 512MB per session
- CPU: 1 core per session  
- Execution timeout: 30s
- File descriptors: 100 per session

**Implementation Path**:
- Use psutil (already imported) for monitoring
- Implement hard limits with subprocess resource controls
- Add graceful degradation as specified
- Create resource cleanup on limit exceeded

**Key Decisions**:
- Enforcement mechanism (SIGTERM vs. exception)
- Warning thresholds (80% of limit?)
- Resource reservation vs. limits

### 2.2 Health Monitoring
**Current State**: HeartbeatMessage exists but underutilized

**Implementation Path**:
- Implement automatic restart on crash (specified line 477)
- Add /proc/{pid}/status memory monitoring (line 488)
- Create health aggregation in manager
- Add circuit breaker for failing sessions

**Key Decisions**:
- Health check frequency vs. overhead
- Restart policy (immediate, backoff, circuit break)
- Metric retention period

### 2.3 Error Handling Enhancement
**Specified Pattern** (from planning doc):
```
what: What went wrong
why: Why it happened  
how: How to fix it
code: ErrorCode enum
```

**Implementation Path**:
- Create structured error types
- Add error code enumeration
- Implement fix suggestions
- Add error recovery actions

## Phase 3: Performance Achievement (Q3 2025)

The unified plan specified ambitious performance targets that require optimization.

### 3.1 Meeting Latency Requirements
**Specified Targets** (lines 372-379):
- Simple expression: 2ms target, 5ms maximum
- Print to client: 5ms target, 10ms maximum
- Session acquisition (warm): 10ms target, 100ms maximum

**Current Reality**: Likely 10-50ms for simple operations

**Optimization Areas**:
- Protocol serialization (MessagePack vs. alternatives)
- Frame buffering strategy
- Output batching (currently 0.001s delay)
- Connection pooling

### 3.2 Throughput Targets
**Specified Requirements** (lines 384-389):
- 1000 operations/second per session
- 100 concurrent sessions per manager
- 10MB/s streaming output bandwidth

**Implementation Path**:
- Benchmark current performance
- Profile bottlenecks
- Optimize hot paths
- Consider io_uring for Linux

### 3.3 Pool Efficiency
**Specified Target**: >80% pool hit rate after warmup

**Implementation Path**:
- Implement metrics collection as specified
- Add predictive pre-warming
- Optimize warmup code execution
- Add session templates

## Phase 4: Advanced Features (Q4 2025)

Beyond the unified plan's scope, these features would differentiate PyREPL3.

### 4.1 Collaborative Sessions
Multiple users in same session (not in original plan)

**Design Considerations**:
- Operational transformation for code sync
- Permission model
- Conflict resolution
- Output attribution

### 4.2 Notebook Support
Jupyter compatibility (mentioned but not specified)

**Implementation Path**:
- .ipynb file format support
- Cell execution model
- Rich output types (images, HTML)
- Kernel protocol compatibility

### 4.3 Language Plugins
Beyond Python execution (future vision)

**Possibilities**:
- JavaScript via Node subprocess
- SQL execution with database connections
- Shell command execution
- R statistical computing

## Phase 5: Ecosystem Integration (2026)

### 5.1 Deployment Patterns
- Kubernetes operator
- Docker compose templates
- Systemd service files
- Cloud formation templates

### 5.2 Monitoring Integration
- Prometheus metrics
- OpenTelemetry traces
- CloudWatch/Datadog adapters
- Grafana dashboards

### 5.3 Client Libraries
- Python SDK
- JavaScript/TypeScript client
- Go client library
- CLI tool

## Technical Debt from Initial Implementation

### Resolved Issues
- **Input handling**: ✅ Thread-based execution model successfully implemented
- **Sync/async bridge**: ✅ Clean separation between user code (threads) and infrastructure (async)

### Immediate Cleanup Needed
- **Type safety**: 13+ type errors in current code
- **Message routing**: Per-execution queues are fragile (acknowledged in plan)
- **Worker lifecycle**: No graceful degradation implemented
- **Testing gaps**: No integration tests for full flow (though threading tests exist)

### Architectural Improvements
- **Session/Manager split**: Currently conflated (noted in analysis)
- **Protocol layer confusion**: MessageTransport vs PipeTransport unclear
- **Missing abstractions**: No sandbox protocol like pyrepl2 had

### Quality Improvements
- Error handling is minimal
- Logging is inconsistent
- No performance benchmarks
- Documentation is sparse

## Research Questions

### From Unified Planning Gaps
1. **Input Override Approach**: ✅ RESOLVED - Thread-based execution with protocol messages proved safe and effective
2. **Checkpoint Portability**: How to handle platform-specific objects?
3. **Transaction Boundaries**: Should transactions span multiple executions?

### Scaling Questions
1. **Distributed Sessions**: Can sessions migrate between hosts?
2. **Checkpoint Sharing**: Can checkpoints be shared across sessions?
3. **Code Caching**: Should compiled code be cached across sessions?

### Integration Questions
1. **Kernel Protocol**: Should we support Jupyter kernel protocol?
2. **LSP Support**: Value of Language Server Protocol integration?
3. **DAP Integration**: Debug Adapter Protocol for debugging support?

## Success Metrics

### Current Achievement (v0.3.0-alpha)
- ✅ input() works without EOFError - Thread-based execution fully operational
- ❌ 3+ concurrent sessions without deadlock - Pool concurrency issue remains
- ❌ WebSocket clients can connect and execute code - API layer not implemented

### Post-Fix Baseline (v0.3.0)
- ✅ input() works for all interactive scenarios
- 3+ concurrent sessions without deadlock  
- WebSocket clients can connect and execute code

### Phase 1 Completion
- Transactions can rollback on failure
- State can be checkpointed and restored
- All specified message types are functional

### Phase 2 Completion
- Resource limits enforced reliably
- Automatic recovery from crashes
- Production monitoring in place

### Phase 3 Completion
- Meet all latency targets from unified plan
- Achieve throughput requirements
- Pool efficiency >80%

### Phase 4 Completion
- Feature parity with Jupyter for basic use cases
- Collaborative editing functional
- 3+ language plugins working

## Risk Assessment

### Technical Risks
1. **Serialization Complexity**: Multi-tier approach may have edge cases
   - Mitigation: Extensive test matrix, clear fallback rules

2. **Performance Targets Unrealistic**: 2ms latency may be unachievable
   - Mitigation: Set realistic targets based on benchmarks

3. **Pool Complexity**: More concurrency issues may emerge
   - Mitigation: Formal verification of pool logic?

### Architecture Risks
1. **Protocol Lock-in**: Current design may limit evolution
   - Mitigation: Version negotiation from start

2. **Subprocess Overhead**: One process per session may not scale
   - Mitigation: Investigate thread-based alternative

3. **Message Routing**: Current pattern may hit limits
   - Mitigation: Redesign before v1.0

## Next Steps

With input handling complete via thread-based execution:

### Immediate Priorities (Remaining Fixes)
1. **Fix session pool deadlocks** - Debug concurrent acquisition issue
2. **Implement API layer** - WebSocket and REST endpoints for network access

### After All Fixes Complete
1. **Validate system thoroughly** - Comprehensive test suite for threading model
2. **Benchmark baseline** - Measure actual vs. specified performance  
3. **Document API** - Enable early adopters with interactive examples
4. **Create examples** - Show real-world interactive usage patterns

### Quick Wins
1. **Basic transaction support** - Simplest feature to add
2. **Filesystem checkpoints** - Most user value
3. **Resource monitoring** - Critical for production
4. **Structured errors** - Improve debugging

### Foundation Work
1. **Performance benchmark suite** - Track improvements
2. **Integration test framework** - Prevent regressions
3. **Client SDK** - Python package for API access
4. **Deployment guide** - Production setup docs

## Technical Positioning

PyREPL3 intends to occupy a specific technical niche between heavyweight container orchestration and lightweight thread pools:

- **More isolated than**: Thread pools, async executors, in-process REPLs
- **More lightweight than**: Docker containers, Kubernetes pods, VMs
- **More stateful than**: Serverless functions, traditional RPC, job queues
- **More managed than**: Raw subprocess spawning, basic process pools

This positions PyREPL3 as infrastructure for building interactive development tools, computational notebooks, and execution services that require both isolation and persistent state.

## Conclusion

PyREPL3's architecture is fundamentally sound, following lessons from exec-py and pyrepl2. With input handling successfully implemented via thread-based execution, one of three critical issues is resolved. The path forward is clear:

1. **Complete the subprocess-isolated execution service** - Fix pool deadlocks, implement API layer
2. **Realize session-oriented RPC vision** - Transactions, checkpointing, restore
3. **Enable multi-language support** - Abstract worker interface, language-specific implementations
4. **Build production infrastructure** - Resource management, monitoring, deployment patterns
5. **Create ecosystem** - Client SDKs, integrations, deployment tools

The architecture's 70/30 split between language-agnostic infrastructure and language-specific workers positions PyREPL3 to eventually support multiple programming languages while maintaining consistent session management, pooling, and API interfaces.

This roadmap should be updated quarterly based on:
- Actual performance measurements
- User feedback and use cases
- Technical discoveries during implementation
- Ecosystem evolution and standards

The immediate focus must be on fixing the two remaining blocking issues (pool deadlocks and API layer), then systematically implementing the unified plan's vision before expanding scope. The successful thread-based execution model for input handling provides a solid foundation for rich interactive features.