# PyREPL3 Architecture Specification

## Document Information
- **Version**: 1.0.0
- **Status**: Draft
- **Last Updated**: 2025-01-03
- **Classification**: Technical Specification

## Executive Summary

PyREPL3 is an advanced Python execution environment that provides async-first code execution with automatic recovery, distributed execution capabilities, and comprehensive security controls. The system leverages Resonate SDK as its durability and orchestration layer, enabling seamless transitions from local development to distributed production deployments without code changes.

### Key Innovations
- Top-level await support without IPython dependencies
- Automatic crash recovery and execution resumption
- Promise-based communication replacing traditional futures
- Capability-based security enforcement
- Zero external dependencies for local development

## System Architecture

### High-Level Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     PyREPL3 System                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │            Resonate Durability Layer                 │  │
│  │                                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │  │
│  │  │   Promises   │  │ Dependencies  │  │ Durable  │ │  │
│  │  │  Management  │  │   Injection   │  │Functions │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────┘ │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              Core Execution Layer                    │  │
│  │                                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │  │
│  │  │    Async     │  │   Threaded   │  │Namespace │ │  │
│  │  │   Executor   │  │   Executor   │  │ Manager  │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────┘ │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │            Capability & Security Layer               │  │
│  │                                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │  │
│  │  │  Capability  │  │   Security   │  │   HITL   │ │  │
│  │  │   Registry   │  │    Policy    │  │ Workflows│ │  │
│  │  └──────────────┘  └──────────────┘  └──────────┘ │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              Transport Layer                         │  │
│  │                                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │  │
│  │  │   Message    │  │   Protocol   │  │  Event   │ │  │
│  │  │   Transport  │  │    Router    │  │  Queue   │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────┘ │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Component Descriptions

#### 1. Resonate Durability Layer
The foundation that provides crash recovery, distributed execution, and orchestration capabilities.

**Responsibilities:**
- Promise lifecycle management for async operations
- Dependency injection for capabilities
- Durable function registration and execution
- State persistence and recovery
- Distributed coordination (remote mode)

**Key Interfaces:**
- `Resonate.local()` - Zero-dependency local mode
- `Resonate.remote()` - Distributed mode with server
- Promise creation, resolution, and correlation
- Dependency registration and retrieval

#### 2. Core Execution Layer
Handles actual Python code execution with support for multiple execution contexts.

**Components:**

**AsyncExecutor:**
- Implements top-level await using `PyCF_ALLOW_TOP_LEVEL_AWAIT` flag
- Performs execution mode detection (async/sync/blocking)
- Manages AST transformation for complex cases
- Handles coroutine lifecycle

**ThreadedExecutor:**
- Executes blocking I/O operations in thread pool
- Provides cancellation support via sys.settrace
- Maintains namespace isolation

**NamespaceManager:**
- Thread-safe namespace operations with RLock
- Preserves engine internals (_, __, ___)
- Implements merge-only update semantics
- Provides durable state persistence

#### 3. Capability & Security Layer
Enforces security policies and manages capability injection.

**Components:**

**Capability Registry:**
- Maintains available capabilities
- Handles dynamic capability injection/removal
- Creates promise-based request handlers

**Security Policy:**
- Defines security levels (SANDBOX to UNRESTRICTED)
- Enforces capability access at injection time
- Provides runtime validation hooks

**HITL Workflows:**
- Manages human-in-the-loop interactions
- Uses promise resolution for user input
- Supports approval and review workflows

#### 4. Transport Layer
Manages communication between components and external systems.

**Components:**

**Message Transport:**
- Handles protocol message serialization
- Manages connection lifecycle
- Provides buffering and retry logic

**Protocol Router:**
- Routes messages to appropriate handlers
- Correlates requests with responses
- Manages message ordering

**Event Queue:**
- Buffers messages when not in async context
- Ensures proper event loop coordination
- Handles backpressure

## Data Flow Patterns

### Code Execution Flow

```
User Code → Execution Request
           ↓
    Mode Detection
    ├─ Top-Level Await → AsyncExecutor + PyCF_ALLOW_TOP_LEVEL_AWAIT
    ├─ Async Functions → AsyncExecutor (standard)
    ├─ Blocking I/O → ThreadedExecutor
    └─ Simple Sync → Direct Execution
           ↓
    Namespace Update (merge-only)
           ↓
    Result/Exception
```

### Capability Invocation Flow

```
Code calls capability (e.g., input())
           ↓
    Capability creates Resonate promise
           ↓
    Request sent via Transport
           ↓
    External system processes request
           ↓
    Response resolves promise
           ↓
    Execution continues with result
```

### Recovery Flow (Remote Mode)

```
Execution starts → Creates durable checkpoint
           ↓
    System crashes
           ↓
    Recovery initiated
           ↓
    Resonate recovers state
           ↓
    Execution resumes from checkpoint
           ↓
    Continues to completion
```

## Deployment Modes

### Local Development Mode

```python
# Zero external dependencies
resonate = Resonate.local()

# Everything works except crash recovery
# Uses in-memory storage
# Single-process execution
# Immediate promise resolution
```

**Characteristics:**
- No server required
- In-memory state storage
- Synchronous promise resolution where possible
- Full functionality except durability
- < 5% performance overhead

### Remote Production Mode

```python
# Requires Resonate server
resonate = Resonate.remote(host="resonate-server")

# Full durability and distribution
# Crash recovery enabled
# Multi-worker support
# Cross-process promise resolution
```

**Characteristics:**
- Requires Resonate server deployment
- Persistent state storage
- Asynchronous promise resolution
- Full crash recovery
- Horizontal scaling support

## Critical Design Decisions

### 1. Namespace Merge-Only Policy
**Decision:** Never replace namespace dictionary, always merge updates.

**Rationale:** 
- Prevents KeyError failures discovered in IPython integration
- Preserves execution engine internals
- Maintains compatibility with display hooks

**Implementation:**
```python
# WRONG - causes KeyError
self._namespace = new_namespace

# CORRECT - preserves internals
self._namespace.update(new_namespace)
```

### 2. PyCF_ALLOW_TOP_LEVEL_AWAIT Flag Usage
**Decision:** Use compile flag 0x1000000 for top-level await support.

**Rationale:**
- Avoids IPython dependency complexity
- Direct Python interpreter support
- Simpler implementation (~400 lines vs 2000+)

### 3. Capability-Level Security
**Decision:** Enforce security at capability injection, not code analysis.

**Rationale:**
- Code-level preprocessors easily bypassed
- Simpler and more robust
- Clear security boundaries

### 4. Promise-Based Communication
**Decision:** Replace futures with Resonate promises throughout.

**Rationale:**
- Automatic durability
- Built-in correlation
- Distributed by design
- HITL support native

## Performance Considerations

### Local Mode Performance Targets
- Execution overhead: < 5% vs direct Python
- Promise resolution: < 1ms local
- Namespace operations: < 100μs
- Capability injection: < 10ms

### Remote Mode Performance Targets
- Promise creation: < 10ms
- State persistence: < 50ms
- Recovery time: < 1 second
- Message routing: < 5ms

### Optimization Strategies
1. Lazy dependency injection
2. Promise batching for bulk operations
3. Namespace snapshot caching
4. Connection pooling for transport
5. AST caching for repeated code

## Error Handling Philosophy

### Fail-Safe Defaults
- Unknown execution mode → ThreadedExecutor
- Promise timeout → Graceful degradation
- Capability unavailable → Clear error message
- Namespace conflict → Preserve existing

### Recovery Strategies
1. **Transient Failures:** Automatic retry with backoff
2. **Persistent Failures:** Checkpoint and await intervention
3. **Security Violations:** Immediate termination
4. **Resource Exhaustion:** Graceful degradation

## Security Architecture

### Defense in Depth
1. **Capability Injection:** First line of defense
2. **Runtime Validation:** Second line of defense
3. **Audit Logging:** Detection and forensics
4. **Resource Limits:** Prevent abuse

### Trust Boundaries
- User code ↔ Execution engine
- Local process ↔ Remote services
- Capabilities ↔ External systems
- Promise resolution ↔ HITL actors

## Extensibility Points

### Custom Capabilities
- Implement Capability base class
- Register with Resonate as dependency
- Define promise-based communication

### Custom Executors
- Extend AsyncExecutor for specialized modes
- Register with execution mode detector
- Maintain namespace compatibility

### Security Policies
- Extend SecurityPolicy class
- Define custom security levels
- Implement validation hooks

## Migration Path

### Phase 1: Wrapper Integration
- Wrap existing executors in durable functions
- Maintain backward compatibility
- Gradual capability migration

### Phase 2: Promise Adoption
- Replace futures with promises
- Enable HITL workflows
- Add recovery points

### Phase 3: Full Integration
- Complete Resonate integration
- Enable distributed execution
- Deprecate legacy patterns

## Non-Functional Requirements

### Reliability
- 99.9% uptime (remote mode)
- Automatic recovery from crashes
- No data loss on failure
- Graceful degradation

### Scalability
- Support 1000+ concurrent executions
- Horizontal scaling capability
- Efficient resource utilization
- Backpressure handling

### Maintainability
- Clear separation of concerns
- Comprehensive logging
- Metric collection
- Version compatibility

### Usability
- Zero-config local development
- Clear error messages
- Progressive disclosure
- Intuitive APIs

## Compliance and Standards

### Python Standards
- PEP 8 code style
- PEP 484 type hints
- PEP 492 async/await
- PEP 3156 asyncio

### Security Standards
- OWASP secure coding
- Principle of least privilege
- Defense in depth
- Audit trail requirements

## Dependencies

### Required Dependencies
- Python 3.8+ (async/await support)
- Resonate SDK
- Standard library modules

### Optional Dependencies
- Resonate server (remote mode)
- Monitoring tools
- Performance profilers

## Testing Requirements

### Unit Testing
- Component isolation
- Mock Resonate interactions
- Namespace operations
- Security policy enforcement

### Integration Testing
- End-to-end execution flows
- Promise resolution chains
- Recovery scenarios
- HITL workflows

### Performance Testing
- Benchmark execution modes
- Stress test promise system
- Memory leak detection
- Concurrency limits

### Security Testing
- Capability bypass attempts
- Resource exhaustion
- Injection attacks
- Privilege escalation

## Documentation Requirements

### User Documentation
- Getting started guide
- API reference
- Migration guide
- Troubleshooting

### Developer Documentation
- Architecture overview
- Component specifications
- Extension guide
- Contributing guidelines

### Operations Documentation
- Deployment guide
- Configuration reference
- Monitoring setup
- Incident response

## Success Metrics

### Technical Metrics
- Code coverage > 90%
- Performance targets met
- Zero critical security issues
- Recovery success rate > 99%

### User Metrics
- Developer adoption rate
- Error rate reduction
- Time to first execution
- Support ticket volume

## Risk Assessment

### Technical Risks
1. **Event loop complexity:** Mitigation via careful coordination
2. **Promise explosion:** Mitigation via cleanup and limits
3. **Namespace corruption:** Mitigation via merge-only policy
4. **Performance regression:** Mitigation via benchmarking

### Operational Risks
1. **Server dependency:** Mitigation via local mode
2. **Network failures:** Mitigation via retry logic
3. **Resource exhaustion:** Mitigation via limits
4. **Version incompatibility:** Mitigation via testing

## Future Considerations

### Planned Enhancements
1. GPU execution support
2. Distributed data structures
3. Advanced debugging tools
4. Performance profiling integration

### Research Areas
1. JIT compilation integration
2. Predictive resource allocation
3. Intelligent retry strategies
4. Automated security analysis

## Appendices

### A. Glossary
- **Capability:** An injectable function providing external functionality
- **Durable Function:** A Resonate-wrapped function with recovery support
- **HITL:** Human-In-The-Loop workflow
- **Promise:** A durable future with automatic correlation

### B. References
- Resonate SDK Documentation
- Python Language Reference
- AsyncIO Documentation
- Security Best Practices

### C. Change Log
- v1.0.0: Initial specification based on REFINED prompts