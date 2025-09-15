# Repository Guidelines

Capsule is a Python execution environment implementing a Subprocess‑Isolated Execution Service (SIES). This guide summarizes how to work effectively in this repo during the transition from ThreadedExecutor to AsyncExecutor.

## Project Structure & Module Organization
- `src/`: library code
  - `src/subprocess/`: executors (`ThreadedExecutor`, `AsyncExecutor` skeleton), `worker.py`
  - `src/session/`: `Session`, `SessionPool`, manager utilities
  - `src/protocol/`: message models, framing, transports
- `tests/`: `unit/`, `integration/`, `e2e/`, `fixtures/`
- `docs/async_capability_prompts/current/`: key specs and implementation notes

## Build, Test, and Development Commands
Note: The project `.venv/` already exists; `uv sync` and `uv run` use it automatically. Activation is optional for editor tooling: `source .venv/bin/activate`.
```bash
uv sync                                   # install/sync dependencies
uv run pytest                             # run all tests
uv run pytest -m unit|integration|e2e     # run by marker
uv run pytest --cov=src --cov-report=term-missing  # coverage (term)
uv run pytest -n auto                     # parallel tests
uv run mypy src/ && uv run basedpyright src/       # type checks
uv run ruff check src/ && uv run black src/ && uv run ruff format src/  # lint/format
uv run pytest --timeout=30                # guard long tests
```

## Coding Style & Naming Conventions
- Python 3.11+, 4‑space indent, type hints for public APIs.
- Names: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE`.
- Formatting: `black`; Lint: `ruff` (follow its import and style rules).
- Namespace rule: never replace dicts; always merge: `self._namespace.update(new)`; preserve `ENGINE_INTERNALS`.
- Event loop: set/get the loop before creating asyncio objects; coordinate threads via `call_soon_threadsafe`.

## Testing Guidelines
- Framework: `pytest` with markers (`unit`, `integration`, `e2e`).
- File naming: `tests/.../test_*.py`; focus tests near the code they validate.
- During transition, expose an async interface (async wrapper over `ThreadedExecutor` as needed).
- Protocol fields must be present (e.g., `ResultMessage.execution_time`; heartbeat metrics).

## Commit & Pull Request Guidelines
- Use Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`; scope optional (e.g., `feat(executor): add async wrapper`).
- Subject in imperative mood, ≤72 chars; include context in body and breaking changes under `BREAKING CHANGE:`.
- PRs: clear description, linked issues, tests/fixtures updated, docs touched when behavior changes; ensure lint, type checks, and tests pass.

## Issue Conventions (agents & maintainers)
- For how we write and manage issues and milestones, see:
  - `docs/PROCESS/ISSUE_CONVENTIONS.md` — covers milestone naming, issue title format, label taxonomy, required sections, per‑workstream invariants, rollout/flags, and a quality checklist.
  - `.github/ISSUE_TEMPLATE/` — ready‑to‑use templates for feature/refactor/hardening and meta/process issues.
  - README “Contributing” — quick links and where to file.
  
Use those references when creating/updating issues so titles, labels, and sections stay consistent and reviewable.

## Security & Configuration Tips
- Each `Session` runs isolated; respect limits (≈512MB memory, 30s timeout, ~100 FDs).
- Do not use `dont_inherit=True` in `compile()` (cancellation breaks).
- Maintain message correlation IDs and merge‑only namespace policy.

## Documentation Practices
- Prefer one canonical document for a topic and link to it from README and here.
- Avoid duplicating guidance across files; update the canonical doc and keep pointers evergreen.

## References
- Issue conventions: `docs/PROCESS/ISSUE_CONVENTIONS.md`
