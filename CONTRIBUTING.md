# Contributing to Capsule

Thank you for your interest in contributing to Capsule! This document provides guidelines and instructions for contributing to the project.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/capsule.git
   cd capsule
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install the package in development mode:
   ```bash
   pip install -e ".[dev]"
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_session.py

# Run with coverage
pytest --cov=src --cov-report=term-missing
```

### Type Checking

```bash
# Run mypy
mypy src/

# Run basedpyright
basedpyright
```

### Code Formatting

```bash
# Format code with black
black src/ tests/

# Check linting with ruff
ruff check src/ tests/
```

## Code Style

- Follow PEP 8 guidelines
- Use type hints for all function signatures
- Maximum line length: 100 characters (configured in pyproject.toml)
- Use descriptive variable and function names
- Add docstrings to all public functions and classes

## Architecture Guidelines

### Core Principles

1. **Subprocess Isolation**: Each session runs in a separate subprocess
2. **Event-Driven**: Prefer event-driven patterns over polling
3. **Single-Reader Invariant**: Maintain single reader for subprocess stdout
4. **Thread Safety**: Use proper synchronization for shared resources

### Key Components

- **Session Manager**: Manages lifecycle of subprocess workers
- **ThreadedExecutor**: Runs user code in dedicated threads
- **Protocol Layer**: Handles message serialization and framing
- **Session Pool**: Manages pre-warmed session instances

## Testing Guidelines

1. Write tests for new features and bug fixes
2. Ensure tests are isolated and don't depend on external state
3. Use `pytest.mark.asyncio` for async tests
4. Mock external dependencies when appropriate
5. Aim for >80% code coverage

## Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and ensure they pass
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Issue Conventions and Templates

We maintain consistent, high‑quality issues so ownership, risks, sequencing, and acceptance criteria are obvious.

- Read: `docs/PROCESS/ISSUE_CONVENTIONS.md` for titles, labels, required sections, rollout/flags, and core invariants by workstream.
- Use GitHub templates when filing issues:
  - Feature / Refactor / Hardening: `.github/ISSUE_TEMPLATE/feature.md`
  - Meta / Process / Docs: `.github/ISSUE_TEMPLATE/meta.md`
- Assign the appropriate milestone (e.g., "Executor & Worker (EW) — Native Async, Pump, Messaging").
- Apply labels for ownership (`touches:*`), risk (`risk:*`), and type (`type:*`). Add `rollout:flagged` for gated features.

## Pull Request Guidelines

- Provide a clear description of the changes
- Reference any related issues
- Ensure all tests pass
- Update documentation if needed
- Add an entry to CHANGELOG.md (unreleased section)

## Debugging and Troubleshooting

- Use targeted unit/integration tests for the component under investigation
- Development artifacts are stored in `.dev/` (not tracked by git)

## Documentation

- Update docstrings for API changes
- Add examples to README.md for new features
- Document architectural decisions in `docs/architecture/`

## Getting Help

- Open an issue for bug reports or feature requests
- Join discussions in existing issues
- Check the documentation in `docs/` for architecture details

## License

By contributing to Capsule, you agree that your contributions will be licensed under the MIT License.
