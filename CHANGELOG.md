# Changelog

All notable changes to PyREPL3 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of PyREPL3
- Subprocess-isolated execution service with managed process pools
- Session-oriented RPC with persistent namespaces
- Interactive input() support via thread-based execution model
- Session pooling with pre-warming for fast acquisition (<100ms)
- Real-time streaming of stdout/stderr with <10ms latency
- Transaction support with configurable rollback policies
- Checkpoint/restore capabilities for complete session state
- Source tracking for function and class definitions
- WebSocket and REST API interfaces
- Automatic health monitoring and crash recovery
- Cooperative cancellation mechanism with sys.settrace
- Event-driven architecture replacing polling patterns

### Fixed
- Worker stdin/stdout initialization using sys.stdin.buffer
- AsyncIterator await bug in session warmup
- Session warmup deadlock with re-entrant lock
- Message type normalization to string literals
- Single-pass evaluation preventing double execution
- Output race condition with queue/pump architecture
- Input() implementation with proper prompt flushing
- SessionPool concurrent creation deadlock

### Changed
- Replaced polling patterns with event-driven mechanisms
- Improved rate limiter with on-demand token computation
- Enhanced SessionPool with hybrid health check pattern

## [0.1.0] - 2024-12-27

### Added
- Core architecture implementation
- Basic session management
- Protocol layer with MessagePack/JSON support
- ThreadedExecutor for blocking I/O support

[Unreleased]: https://github.com/your-username/pyrepl3/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-username/pyrepl3/releases/tag/v0.1.0