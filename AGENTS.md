# Repository Guidelines

This guide helps contributors work effectively in this repository. It covers structure, build/test commands, style, testing, PR etiquette, and the core invariants that must not be broken.

## Project Structure & Module Organization
- `src/`
  - `src/subprocess/` — execution engine: `executor.py` (ThreadedExecutor), `async_executor.py` (native async paths; worker routing pending), `worker.py`, `namespace.py`.
  - `src/session/` — `Session`, `SessionPool`, lifecycle/orchestration.
  - `src/protocol/` — message schemas (`messages.py`), framing (`framing.py`), transport (`transport.py`).
  - `src/integration/` — local Resonate bridge, DI wiring, capabilities.
- `tests/` — `unit/`, `integration/`, `e2e/`, `fixtures/`.
- `docs/` — roadmap and process docs (see `docs/PROCESS/ISSUE_CONVENTIONS.md`).

## Build, Test, and Development Commands
- Install/sync deps: `uv sync`
- Run tests: `uv run pytest` (all), `uv run pytest -m unit|integration|e2e`
- Coverage: `uv run pytest --cov=src --cov-report=term-missing`
- Types & lint/format: `uv run mypy src/ && uv run basedpyright src/` and `uv run ruff check src/ && uv run ruff format src/`
- Guard long tests: `uv run pytest --timeout=30`

## Coding Style, Typing & Naming
- Python 3.11+, 4‑space indent, type hints on public APIs.
- Typing: strong/strict across the codebase (not just public APIs). Avoid `Any`; prefer `Protocol`, `TypedDict`, and generics. Add minimal local stubs under `typings/` for third‑party gaps. See `docs/TYPING.md`.
- Naming: modules/functions `snake_case`; classes `PascalCase`; constants `UPPER_SNAKE`.
- Linting & formatting: Ruff (configured in `pyproject.toml`). Type checks: mypy (strict) + basedpyright (strict).
- Repository‑critical invariants:
  - Single‑reader transport (Session is the only reader).
  - Output‑before‑result (worker drains the output pump before sending Result; timeout → Error and no Result).
  - Merge‑only namespace (preserve `ENGINE_INTERNALS`; never replace the namespace dict).
  - Event loop ownership (use `asyncio.get_running_loop()`; coordinate threads with `call_soon_threadsafe`; do not create loops in durable layers).
  - Pump‑only outputs (stdout/stderr go through the async pump; avoid direct writes).

## Testing Guidelines
- Framework: `pytest` with markers (`unit`, `integration`, `e2e`).
- Test files: `tests/**/test_*.py`; place tests near the code they validate.
- Prefer event‑driven waits (Conditions/Events) over sleeps; avoid flaky timing.
- Coverage target: ≥ 70% on core modules.
- Examples:
  - Unit only: `uv run pytest -m unit`
  - Coverage summary: `uv run pytest --cov=src --cov-report=term-missing`

## Commit & Pull Request Guidelines
- Conventional Commits (e.g., `feat:`, `fix:`, `refactor:`, `test:`, `docs:`); subject ≤ 72 chars; describe scope and impact.
- PRs: clear description, linked issues, “Affected Paths” listed, risks/invariants noted; update docs when behavior changes.
- CI must pass: tests, type checks, Ruff (lint+format). Use the templates and conventions in `docs/PROCESS/ISSUE_CONVENTIONS.md`.

## Security & Configuration Tips
- Execution is subprocess‑isolated; respect resource/time limits.
- Do not set `dont_inherit=True` in `compile()` (breaks cancellation tracing).
- Keep protocol ordering guarantees; do not add new transport readers.

## References
- Issue conventions and templates: `docs/PROCESS/ISSUE_CONVENTIONS.md`, `.github/ISSUE_TEMPLATE/`
