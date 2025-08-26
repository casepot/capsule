# PyREPL3 Planning Prompts

This directory contains focused planning prompts following the PARIS methodology (Problem Archaeology, Architecture Recognition, Risk Illumination, Implementation Scaffolding, Success Validation) for fixing and completing PyREPL3's core functionality.

## Overview

These prompts were created after deep comparative analysis of PyREPL3 with its predecessors (pyrepl2 and exec-py). Each prompt guides a planner through investigating and implementing a specific fix or feature with clear context, constraints, and success criteria.

## Implementation Order

### Phase 1: Critical Fixes (Days 1-2)
**Must complete before anything else works properly**

1. **[01_input_override_persistence.md](01_input_override_persistence.md)** 
   - Fix the bug where input() doesn't persist between executions
   - Simple one-line fix at executor.py:199
   - Enables interactive code to work across multiple executions

2. **[02_session_reuse_pattern.md](02_session_reuse_pattern.md)**
   - Fix namespace persistence by properly reusing sessions
   - Update test patterns to use fixtures or SessionPool
   - Critical for variables, functions, and imports to persist

### Phase 2: Core Features (Days 3-4)
**Implement missing functionality**

3. **[03_transaction_implementation.md](03_transaction_implementation.md)**
   - Add transaction support with namespace snapshots
   - Enable rollback on failure, commit on success
   - Essential for safe experimentation

4. **[04_checkpoint_restore_system.md](04_checkpoint_restore_system.md)**
   - Complete checkpoint/restore with source preservation
   - Multi-tier serialization for compatibility
   - Enables session persistence and sharing

### Phase 3: Optimization (Day 5)
**Improve reliability and performance**

5. **[05_output_streaming_simplification.md](05_output_streaming_simplification.md)**
   - Simplify over-engineered output capture
   - Fix large output (>1MB) issues
   - Reduce complexity while maintaining real-time streaming

### Phase 4: API Layer (Days 6-7)
**Enable network access**

6. **[06_api_layer_integration.md](06_api_layer_integration.md)**
   - Implement WebSocket and REST endpoints
   - Bridge session management with network layer
   - Complete the vision of networked execution service

## How to Use These Prompts

Each prompt follows the PARIS methodology structure:

1. **Mission Statement**: Clear goal and constraints
2. **Context Gathering**: What must be understood before implementing
3. **Planning Methodology**: How to approach the problem
4. **Output Requirements**: Specific deliverables expected
5. **Calibration**: Tuning for the planner's approach
6. **Success Criteria**: Measurable validation requirements

### For Planners

When using these prompts:

1. **Read the entire prompt first** - Understand the full context
2. **Follow the investigation phase** - Don't skip discovery
3. **Consider all approaches** - Even if one is recommended
4. **Validate assumptions** - Test your understanding
5. **Document decisions** - Explain why you chose an approach

### For Implementers

After planning is complete:

1. **Follow the plan precisely** - Especially file:line specifications
2. **Run tests immediately** - Verify each fix works
3. **Check for regressions** - Ensure existing tests pass
4. **Document changes** - Update relevant documentation

## Key Insights from Analysis

### From pyrepl2
- **Subprocess persistence**: Keep subprocess alive for session duration
- **Source preservation**: Extract and save function/class source code
- **Session pooling**: Pre-warm and reuse sessions efficiently

### From exec-py
- **Input override**: Simple namespace override: `local_ns["input"] = await_input`
- **Transactions**: Namespace snapshots with dict copy
- **Thread execution**: Run user code in threads for blocking I/O

### PyREPL3's Issues
- **Architecture is sound** - Has all the pieces, just not connected properly
- **Over-engineering** - Output streaming is unnecessarily complex
- **Simple bugs** - Input override restoration breaks persistence

## Success Metrics

After all fixes are implemented:

| Feature | Current State | Target State | Test |
|---------|--------------|--------------|------|
| Input persistence | ❌ Resets each execution | ✅ Persists | `test_input_persistence` |
| Namespace persistence | ❌ New subprocess each test | ✅ Reuses session | `test_namespace_persistence` |
| Transactions | ❌ Not implemented | ✅ Rollback works | `test_transaction_rollback` |
| Checkpoints | ❌ Not implemented | ✅ Save/restore | `test_checkpoint_restore` |
| Large output | ⚠️ Returns 0 bytes | ✅ Streams correctly | `test_large_output` |
| API Layer | ❌ Not implemented | ✅ WebSocket + REST | `test_api_endpoints` |

## Architecture After Fixes

```
┌─────────────────────────────────────────────┐
│                API Layer                     │
│  - FastAPI (REST + WebSocket)               │
│  - Client session mapping                    │
│  - Authentication/rate limiting              │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│           Session Management                 │
│  - SessionPool (with proper reuse)          │
│  - Session lifecycle tracking                │
│  - Resource limits enforcement               │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│          Subprocess Worker                   │
│  - Persistent namespace (fixed)              │
│  - ThreadedExecutor for blocking I/O         │
│  - Transaction support (new)                 │
│  - Checkpoint/restore (new)                  │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│          Protocol Layer                      │
│  - Binary framed messages                    │
│  - INPUT/INPUT_RESPONSE (fixed)             │
│  - Simplified output streaming (new)         │
└──────────────────────────────────────────────┘
```

## Next Steps After Fixes

Once all fixes are implemented:

1. **Comprehensive Testing** - Full integration test suite
2. **Performance Benchmarking** - Measure against targets
3. **Documentation** - API documentation and examples
4. **Client SDKs** - Python, JavaScript clients
5. **Deployment Guide** - Production setup instructions

## Resources

- [PARIS Methodology](../prompt-engineering-methodology/)
- [Comparative Analysis](../docs/REFINED_COMPARATIVE_ANALYSIS.md)
- [Actionable Fixes](../docs/REFINED_ACTIONABLE_FIXES.md)
- [ROADMAP](../ROADMAP.md)
- [Test Foundation](../test_foundation/)

## Contributing

When adding new planning prompts:

1. Follow the PARIS methodology structure
2. Include clear context from problem analysis
3. Specify measurable success criteria
4. Provide concrete implementation guidance
5. Document integration points with existing fixes

Remember: These prompts guide investigation and planning. Encourage planners to discover solutions rather than just implementing prescriptive fixes.