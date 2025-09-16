# Contributing to Capsule

Thank you for your interest in contributing to Capsule! This document provides guidelines and instructions for contributing to the project.

## Development Setup

We use `uv` for dependency management and running tasks.

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/capsule.git
   cd capsule
   ```

2. Install/sync dependencies:
   ```bash
   uv sync
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_session.py

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing

# Guard long tests
uv run pytest --timeout=30
```

### Type Checking

```bash
# mypy (strict)
uv run mypy src/

# basedpyright (strict)
uv run basedpyright src/
```

### Linting & Formatting (pyproject.toml)

```bash
# Lint code with ruff
uv run ruff check src/ tests/

# Format code with ruff
uv run ruff format src/ tests/
```

## Code Style

- Python 3.11+
- Strong typing across the codebase; avoid `Any` where possible. See `docs/typing-guidelines.md` for tools, policies, and where typing is deliberately loose (with rationale).
- Respect linters/formatters configured in `pyproject.toml`.
- Public APIs should have type hints and docstrings.

## Architecture & Invariants

For workstream-specific invariants (source of truth), see:

- docs/issue-conventions.md#workstream-core-invariants

Examples include: single-reader transport, output-before-result ordering, merge-only namespace updates, pump-only outputs, and event loop ownership. Do not duplicate these here; link to the doc above in PRs/issues.

## Testing Guidelines

1. Write tests for new features and bug fixes
2. Prefer event-driven waits (Conditions/Events) over sleeps
3. Use `pytest.mark.asyncio` for async tests
4. Mock external dependencies when appropriate
5. Coverage target: ≥ 70% on core modules (see CI config)

## Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and ensure they pass
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Issue Conventions and Templates

The conventions document is the source of truth for issue structure, labels, and invariants:

- docs/issue-conventions.md

Use GitHub templates when filing issues (do not duplicate guidance in the issue body):
- Feature / Refactor / Hardening: `.github/ISSUE_TEMPLATE/feature.md`
- Meta / Process / Docs: `.github/ISSUE_TEMPLATE/meta.md`
- General skeleton (copyable body for quality passes): `.github/ISSUE_TEMPLATE.md`

Apply labels for ownership (`touches:*`), risk (`risk:*`), type (`type:*`), and rollout (`rollout:*`) as appropriate. Assign the relevant milestone.

## Pull Request Guidelines

- Provide a clear description of the changes
- Reference any related issues and link relevant docs/specs (use references; don’t paste long excerpts)
- Ensure all tests pass (CI must pass: tests, type checks, Ruff)
- Update documentation if needed
- Add an entry to CHANGELOG.md (unreleased section)

## Debugging and Troubleshooting

- Use targeted unit/integration tests for the component under investigation
- Development artifacts are stored in `.dev/` (not tracked by git)

## Documentation

- Update docstrings for API changes
- Add examples to README.md for new features
- Document architectural decisions in the focused guides under `docs/` (e.g., `architecture-overview.md`, `execution-engine.md`, `session-runtime.md`); link from PRs instead of inlining.

## Getting Help

- Open an issue for bug reports or feature requests
- Join discussions in existing issues
- Check the documentation in `docs/` for architecture details

## License

By contributing to Capsule, you agree that your contributions will be licensed under the MIT License.
