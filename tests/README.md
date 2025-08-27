# PyREPL3 Test Suite

## Overview

The PyREPL3 test suite is organized by test scope and purpose, following best practices for Python testing with pytest.

## Test Structure

```
tests/
├── unit/           # Fast, isolated unit tests
├── integration/    # Component integration tests  
├── features/       # Feature-specific tests
├── e2e/           # End-to-end tests
├── regression/    # Regression tests for fixed bugs
├── stress/        # Performance and stress tests
├── fixtures/      # Shared test fixtures
└── conftest.py    # Pytest configuration
```

### Test Categories

#### Unit Tests (`unit/`)
- Fast, isolated tests of individual components
- No external dependencies or I/O
- Run time: <1s per test
- **Markers**: `@pytest.mark.unit`

#### Integration Tests (`integration/`)
- Test interaction between components
- May involve subprocess creation
- Run time: 1-5s per test
- **Markers**: `@pytest.mark.integration`

#### Feature Tests (`features/`)
- Test specific features end-to-end
- Validate complete functionality
- Run time: varies
- **Markers**: Feature-specific

#### End-to-End Tests (`e2e/`)
- Complete user scenarios
- Full system validation
- Run time: 5-30s per test
- **Markers**: `@pytest.mark.e2e`, `@pytest.mark.slow`

#### Regression Tests (`regression/`)
- Prevent fixed bugs from returning
- Document historical issues
- Run time: varies
- **Markers**: `@pytest.mark.regression`

#### Stress Tests (`stress/`)
- Performance testing
- Load testing
- Concurrent execution testing
- **Markers**: `@pytest.mark.stress`, `@pytest.mark.slow`

## Running Tests

### Run all tests
```bash
uv run pytest tests/
```

### Run specific test categories
```bash
# Unit tests only
uv run pytest tests/unit -m unit

# Integration tests
uv run pytest tests/integration -m integration

# Feature tests
uv run pytest tests/features/

# Fast tests only (exclude slow)
uv run pytest tests/ -m "not slow"

# Specific feature
uv run pytest tests/features/test_cancellation.py
```

### Run with coverage
```bash
uv run pytest tests/ --cov=src --cov-report=html
```

### Run in parallel
```bash
uv run pytest tests/ -n auto
```

## Test Markers

Tests can be marked with the following markers:

- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.slow` - Tests taking >1s
- `@pytest.mark.stress` - Performance/stress tests
- `@pytest.mark.regression` - Regression tests
- `@pytest.mark.skip_ci` - Skip in CI environments

## Writing Tests

### Using Fixtures

```python
import pytest
from tests.fixtures.sessions import create_session, SessionHelper
from tests.fixtures.messages import MessageFactory, assert_output_contains

@pytest.mark.integration
class TestExample:
    @pytest.mark.asyncio
    async def test_with_session(self):
        async with create_session() as session:
            messages = await SessionHelper.execute_code(session, "print('test')")
            assert_output_contains(messages, "test")
```

### Adding New Tests

1. Choose the appropriate directory based on test scope
2. Use descriptive test names
3. Add appropriate markers
4. Use shared fixtures when possible
5. Keep tests focused and isolated

## CI/CD Integration

### Recommended CI Pipeline

```yaml
# Fast feedback (every commit)
- run: uv run pytest tests/unit -m unit

# PR validation
- run: uv run pytest tests/ -m "not stress and not slow"

# Nightly/Release
- run: uv run pytest tests/
```

## Debug Tests Archive

Historical debug tests used during development are archived in `.dev/debug_tests/` for reference but are not part of the main test suite.

## Test Coverage Goals

- Unit tests: >80% coverage
- Integration tests: Critical paths covered
- E2E tests: Main user workflows
- Regression tests: All fixed bugs

## Contributing

When adding new functionality:
1. Write unit tests first (TDD)
2. Add integration tests for component interactions
3. Create e2e tests for user-facing features
4. Add regression tests when fixing bugs