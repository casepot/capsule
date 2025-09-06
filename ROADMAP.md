# Capsule Development Roadmap

> Last Updated: 2025-09-06 | Version: 0.1.0-dev

## Current Status

Capsule has completed Phases 0-2c of its foundation development, establishing core infrastructure for subprocess-isolated Python execution with local-mode promise orchestration.

### Implementation Status by Component

| Component | Status | Coverage | Notes |
|-----------|--------|----------|-------|
| **Protocol Layer** | ✅ Complete | 75% | Message framing, serialization working |
| **Session Management** | ✅ Complete | 66% | Single-loop invariant, interceptors working |
| **ThreadedExecutor** | ✅ Complete | 59% | Async wrapper, blocking I/O support |
| **AsyncExecutor** | 🚧 Skeleton | 89% | Delegates to ThreadedExecutor, no native async |
| **Namespace Manager** | ✅ Complete | 62% | Merge-only policy, ENGINE_INTERNALS protected |
| **ResonateProtocolBridge** | ✅ Complete | 76% | Execute/Result/Error and Input correlation |
| **Capabilities** | 🔶 Minimal | 100% | Only InputCapability implemented |
| **Worker** | ✅ Complete | 68% | Checkpoint/restore, output ordering, busy guard |
| **Remote Mode** | ❌ Not Started | 0% | Design complete, no implementation |

### Test Metrics
- **Unit Tests**: 164/166 passing (98.8%)
- **Integration Tests**: 36/40 passing (90%)
- **Overall Coverage**: ~56%
- **Performance**: Not benchmarked

## Completed Work (Phases 0-2c)

### Phase 0: Emergency Fixes ✅
- ThreadedExecutor async wrapper for test compatibility
- Namespace merge-only policy implementation
- Event loop management fixes
- Message protocol completeness

### Phase 1: AsyncExecutor Foundation ✅
- Execution mode detection (AST analysis)
- PyCF_ALLOW_TOP_LEVEL_AWAIT constant (0x2000)
- Blocking I/O detection with attribute chains
- DI factory pattern (async_executor_factory)
- Configurable timeouts and cache sizes

### Phase 2: Promise-First Integration ✅
- Durable functions using ctx.promise pattern
- Complete protocol correlation (Execute/Result/Error, Input/InputResponse)
- Session interceptors for message routing
- Worker stabilization (output ordering, checkpoint/restore)
- Single-loop invariant enforcement

## Immediate Priorities (Phase 3: Native Async)

**Goal**: Complete AsyncExecutor to handle async code natively without ThreadedExecutor delegation.

### Deliverables (3-4 days estimated)

#### 3.1 EventLoopCoordinator
```python
# Target implementation
- ensure_event_loop() - Detect/create loops safely
- queue_for_async() - Queue coroutines when not in async context
- flush_queue() - Execute queued operations
```

#### 3.2 CoroutineManager
```python
# Target implementation
- track_coroutine() with weak references
- track_task() for asyncio.Task lifecycle
- cleanup() with proper stats
```

#### 3.3 ExecutionCancellation
```python
# Target implementation
- cancel_execution() for running code
- check_cancelled() periodic checks
- cancellable_execution() context manager
```

#### 3.4 Native Execution Paths
- Implement `_execute_top_level_await()` using PyCF_ALLOW_TOP_LEVEL_AWAIT
- Complete AST transformation fallback
- Remove ThreadedExecutor delegation for async code

### Success Criteria
- [ ] AsyncExecutor handles all execution modes natively
- [ ] Proper coroutine cleanup and cancellation
- [ ] Event loop coordination without conflicts
- [ ] All unit tests passing with native implementation

## Near-Term Goals (Phase 4: Capability System)

**Goal**: Build comprehensive capability system for controlled I/O and system access.

### Core Capabilities (3-4 days estimated)

#### 4.1 File Capabilities
- FileReadCapability
- FileWriteCapability
- FileListCapability

#### 4.2 Network Capabilities
- FetchCapability (HTTP/HTTPS)
- WebSocketCapability
- DatabaseCapability

#### 4.3 System Capabilities
- EnvironmentCapability
- TimeCapability
- ProcessCapability

#### 4.4 Security Framework
- SecurityPolicy enforcement
- Capability registry
- Runtime validation hooks
- Audit logging

### Success Criteria
- [ ] All capabilities from spec implemented
- [ ] Security boundaries enforced at injection
- [ ] HITL workflows functional
- [ ] Comprehensive test coverage

## Medium-Term Vision (Phase 5: Remote & Production)

**Goal**: Enable distributed execution and production-ready features.

### 5.1 Remote Resonate Mode (3-4 days estimated)
- Server connection management
- Authentication/authorization
- Distributed promise resolution
- Retry logic with exponential backoff
- Circuit breakers

### 5.2 Production Hardening
- Resource limits enforcement (memory, CPU, FDs)
- Graceful degradation strategies
- Connection pooling
- MigrationAdapter for incremental adoption

### Success Criteria
- [ ] Works with remote Resonate server
- [ ] Handles network failures gracefully
- [ ] Production-ready reliability
- [ ] Performance targets met

## Long-Term Vision (Phase 6: Performance & Observability)

**Goal**: Enterprise-grade monitoring and performance.

### 6.1 Performance Optimization (2-3 days estimated)
- AST cache optimization
- Promise batching
- Connection pooling improvements
- Output streaming optimization

### 6.2 Observability
- OpenTelemetry integration
- Prometheus metrics
- Structured logging throughout
- Performance profiling hooks

### 6.3 Benchmarks
- Establish performance baselines
- CI performance gates
- Memory leak detection
- Concurrency stress tests

### Target Metrics
- Simple execution: <5ms
- Top-level await: <10ms  
- Promise resolution: <1ms (local)
- Session acquisition: <100ms
- Throughput: 1000+ ops/sec

## Future Exploration (6+ months)

### Multi-Language Support
- JavaScript/TypeScript worker
- Go worker
- Rust worker
- Common protocol sharing

### Advanced Features
- GPU execution support
- Distributed data structures
- Time-travel debugging
- Notebook kernel implementation

### AI Integration
- LLM-optimized execution patterns
- Streaming for real-time feedback
- Semantic checkpoints
- Agent framework support

## Technical Debt & Improvements

### Immediate (During Phase 3)
- [ ] Fix failing integration tests (4 remaining)
- [ ] Increase test coverage to >70%
- [ ] Document internal APIs
- [ ] Clean up TODO comments in code

### Ongoing
- [ ] Performance benchmarking framework
- [ ] Integration test reliability
- [ ] Error message improvements
- [ ] Developer documentation

## Risk Assessment

### Technical Risks
| Risk | Impact | Mitigation | Status |
|------|--------|------------|--------|
| Event loop complexity | High | Careful coordination, extensive testing | 🟡 Mitigating |
| Promise memory leaks | Medium | Cleanup hooks, monitoring | 🟢 Addressed |
| Namespace corruption | High | Merge-only policy | ✅ Resolved |
| Performance regression | Medium | Benchmarking needed | 🔴 Not started |

### Adoption Risks
| Risk | Impact | Mitigation | Status |
|------|--------|------------|--------|
| Complex API | High | Clear documentation, examples | 🟡 In progress |
| No production users | High | Focus on stability first | 🟡 Foundation laid |
| Limited capabilities | Medium | Phase 4 priority | 🔴 Planned |

## Success Metrics

### Phase 3 Completion
- Native async execution working
- No ThreadedExecutor delegation for async code
- All execution modes properly routed
- Cancellation support functional

### Phase 4 Completion
- 5+ capabilities implemented
- Security policy enforcement working
- HITL workflows tested
- Integration tests >95% passing

### Phase 5 Completion
- Remote mode functional
- Production deployment possible
- Performance targets met
- Recovery mechanisms tested

### Phase 6 Completion
- Full observability stack
- Performance benchmarks established
- <1% performance regression tolerance
- Production-ready certification

## Development Philosophy

1. **Correctness over features** - Get the foundation right
2. **Test everything** - Maintain high test coverage
3. **Document as you go** - Keep documentation current
4. **Incremental progress** - Small, reviewable changes
5. **Honest communication** - Be clear about limitations

## How to Contribute

### Current Needs
- Phase 3: Native AsyncExecutor implementation
- Test coverage improvements
- Documentation updates
- Bug fixes for failing integration tests

### Getting Started
1. Read [FOUNDATION_FIX_PLAN.md](FOUNDATION_FIX_PLAN.md)
2. Check current test status: `uv run pytest`
3. Pick an issue from Phase 3 deliverables
4. Submit small, focused PRs

## Revision History

- **2025-09-06**: Complete rewrite to reflect actual implementation status
- **Previous**: Original aspirational roadmap (archived)