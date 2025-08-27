# PyREPL3 Documentation

Welcome to the PyREPL3 documentation. This directory contains technical documentation, architecture guides, and development resources.

## Documentation Structure

### Architecture (`architecture/`)
Core system architecture and design patterns:
- `session-pool-architecture.md` - Session pool design and implementation
- `event_driven_patterns.md` - Event-driven patterns replacing polling
- `technical_explorations/` - Deep dives into technical decisions
  - `architectural_invariants.md` - Core invariants the system maintains
  - `async_execution_models.md` - Async execution model analysis
  - `beyond_repl.md` - Vision for extending beyond REPL functionality
  - `concurrency_patterns.md` - Concurrency patterns used in the codebase
  - `evaluation_strategies.md` - Code evaluation strategies
  - `implementation_archaeology.md` - Historical implementation decisions
  - `language_boundary.md` - Language boundary handling

### Development (`development/`)
Development guides and implementation details:
- `ACTIONABLE_FIXES.md` - Specific fixes that can be applied
- `COMPARATIVE_ANALYSIS_REPORT.md` - Comparison with similar projects
- `CRITICAL_FIXES_IMPLEMENTED.md` - Critical fixes that have been applied
- `REMAINING_ISSUES.md` - Known issues and future work
- `methodology/` - Development methodology and best practices

### Async Patterns (`async-patterns/`)
Detailed async/await patterns and best practices:
- Event vs Condition variable patterns
- Protocol framing patterns
- Core async principles

### Investigations (`investigations/`)
Historical investigations and troubleshooting:
- `ASYNC_TIMEOUT_INVESTIGATION_REPORT.md` - Async timeout investigation
- `CONCURRENT_SESSIONS_DEADLOCK_FIX.md` - Deadlock fix documentation
- `TRANSPORT_INVESTIGATION_REPORT.md` - Transport layer investigation
- `troubleshooting/` - Troubleshooting logs and analysis
  - `investigation_log.json` - Complete investigation history

## Quick Links

### For Users
- [Main README](../README.md) - Project overview and usage
- [ROADMAP](../ROADMAP.md) - Future development plans
- [CHANGELOG](../CHANGELOG.md) - Version history

### For Contributors
- [CONTRIBUTING](../CONTRIBUTING.md) - Contribution guidelines
- [Architecture Overview](architecture/session-pool-architecture.md)
- [Event-Driven Patterns](architecture/event_driven_patterns.md)

### For Developers
- [Development Methodology](development/methodology/) 
- [Technical Explorations](architecture/technical_explorations/)
- [Investigation History](investigations/troubleshooting/investigation_log.json)

## Key Concepts

1. **Subprocess Isolation**: Each session runs in an isolated subprocess
2. **Session-Oriented RPC**: Persistent state across executions
3. **Event-Driven Architecture**: No polling, everything is event-based
4. **Thread-Based Execution**: User code runs in threads for blocking I/O
5. **Protocol-Based IPC**: Structured message passing over pipes

## Architecture Highlights

- **Worker Process**: Executes Python code in isolation
- **Session Manager**: Manages worker lifecycle
- **Session Pool**: Pre-warmed sessions for fast acquisition
- **Protocol Layer**: Binary framed messages with MessagePack
- **Input Protocol**: Special handling for interactive input()
- **Cancellation**: Cooperative cancellation via sys.settrace

## Getting Started

1. Read the [Architecture Overview](architecture/session-pool-architecture.md)
2. Understand [Event-Driven Patterns](architecture/event_driven_patterns.md)
3. Review [Technical Explorations](architecture/technical_explorations/)
4. Check [Investigation History](investigations/troubleshooting/investigation_log.json) for context