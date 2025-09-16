# Typing Guidelines

> Status: Authoritative reference for Capsule’s typing policy (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if code has drifted, double-check the current sources on your working commit, capture differences that affect your task, and raise any doc gaps to the user while you proceed with up-to-date information).

## Purpose
Capsule treats static typing as a first-class review gate: all runtime and integration code is annotated, and both mypy and basedpyright run in strict modes to prevent `Any` from leaking across subsystem boundaries (`pyproject.toml:20`, `pyproject.toml:42`). This guide replaces `docs/_legacy/TYPING.md` and documents today’s contracts (where `Any` is still intentional) so changes to executors, protocol surfaces, or integration shims can stay aligned.

## Tooling & Configuration
- **Checkers** — mypy runs in `strict` mode with the Pydantic v2 plugin, explicit `Any` guards, and local stub search rooted at `typings/` (`pyproject.toml:42`, `pyproject.toml:61-69`). basedpyright mirrors the same strictness, enabling unknown-type diagnostics as warnings so developers see gaps without blocking installs (`pyproject.toml:73-90`).
- **Dependencies** — the `dev` extra installs both checkers plus third-party stub packages like `types-psutil` and `types-aiofiles` so local runs match CI (`pyproject.toml:20-33`).
- **Commands** — run `uv run mypy src/` and `uv run basedpyright src/` before sending a PR; the contributing guide spells out the exact commands and expectation that both pass cleanly (`CONTRIBUTING.md:38-63`).
- **CI coverage** — the unit-test workflow currently executes pytest and coverage only, so type checks rely on developer discipline (`.github/workflows/unit-tests.yml:1-39`). Breaking changes to typing must therefore update tests *and* run both checkers locally.

## Local Stubs & Third-Party Coverage
Two local stub packages live under `typings/` and are wired through `mypy_path`/`extraPaths`:
- `typings/msgpack/__init__.pyi` captures the `packb`/`unpackb` signatures we depend on while mypy ignores the upstream gap (`typings/msgpack/__init__.pyi:1-17`, `pyproject.toml:67-69`).
- `typings/resonate/__init__.pyi` models the subset of the Resonate SDK used by the local bridge so integration code can stay type-safe without bundling the full SDK surface (`typings/resonate/__init__.pyi:5-28`).

Prefer adding or extending these stubs—or introducing a new leaf under `typings/`—instead of sprinkling `ignore_missing_imports`. When a library publishes an official `py.typed` distribution, swap the local stub for a dependency override and remove the ignore.

## Conventions
### Annotate public runtime APIs
Classes and functions that make up the runtime surface carry concrete annotations, including namespace types, queue payloads, and protocol bridges. Examples include the `SessionInfo` dataclass (typed metadata map) and the `Session` constructor arguments (`src/session/manager.py:45-104`), plus the `ThreadedExecutor` queue item alias `OutputOrSentinel` and sentinel dataclasses used to coordinate pump state (`src/subprocess/executor.py:91-139`, `src/subprocess/executor.py:239-376`). Follow this pattern when adding new entry points or attributes; reviewers should never guess at public signatures.

### Use structured models for protocol traffic
Protocol payloads are enforced via Pydantic models with precise Literal unions and enum-backed discriminators, ensuring downstream code never sees untyped dicts (`src/protocol/messages.py:9-208`). Any new message class must keep literals and field annotations consistent so both mypy and runtime validation agree.

### Deliberate dynamic surfaces (documented `Any`)
The following uses of `Any` are intentional and should not be narrowed without a design change:
- **Execution namespace** — `NamespaceManager` stores the live REPL namespace as `dict[str, Any]` and selectively guards engine internals; user code legitimately injects arbitrary objects (`src/subprocess/namespace.py:23-125`).
- **Result values** — `ResultMessage.value` carries whatever object user code returned and is serialized opportunistically; narrowing would break API parity (`src/protocol/messages.py:77-83`).
- **Durable bridges** — Resonate’s `DurableResult.result` stays `Any` because the bridge simply passes on provider payloads (`src/integration/types.py:6-14`).
- **Session metadata** — callers may stash arbitrary diagnostics in `SessionInfo.metadata` (`src/session/manager.py:45-104`).

When pass-through data does not need to be inspected, prefer `object` over `Any`; reserve `Any` for values that Capsule actively manipulates. If a new surface must loosen types, describe the rationale in code comments and update this document.

### Typed helpers and narrowing
Threaded components should provide narrowly typed helpers instead of unsafely casting call sites. For example, `ThreadSafeOutput` and `_enqueue_from_thread` keep `StreamType` fidelity while managing asynchronous queues (`src/subprocess/executor.py:132-412`). Async control paths should likewise expose typed hooks; prefer `cast` or dedicated helper functions over global ignores when routing union-typed messages.

## Escape Hatches & Suppressions
Use suppressions only when an upstream stub or decorator prevents precise typing, and annotate the reason inline. Current examples include the worker’s `asyncio.create_task` call, which ignores the mismatch between the union-typed `Message` dispatcher and the executor’s `ExecuteMessage` parameter (`src/subprocess/worker.py:514-534`), and the Resonate registration decorator, where the SDK lacks type metadata for the returned wrapper (`src/integration/resonate_functions.py:27-133`). New `# type: ignore[...]` comments must specify the diagnostic code when available and add a short explanation so reviewers know when to revisit the escape hatch.

## Maintenance Workflow
Run both strict checkers locally (`uv run mypy src/`, `uv run basedpyright src/`) before pushing commits, and add focused unit tests whenever typing changes guard critical invariants (e.g., namespace merging or protocol routing). When modifying protocol schemas or executor configuration, update the relevant TypedDicts/Pydantic models and ensure local stubs still cover third-party dependencies. Revisit this guide whenever intentional `Any` usage changes or new stubs are introduced so downstream contributors understand the rationale.

## Planned Updates
- **Executor configuration plumbing (#49)** — `EW-012` will extend `SessionConfig` with typed executor settings and environment parsing; once it lands, document any new config dataclasses or `Any` allowances it introduces so session authors know how to annotate overrides.
- **Async executor routing (#51)** — `EW-010` will let the worker delegate top-level await code to `AsyncExecutor`. Expect additional typed entry points (e.g., active async executor references) and update the suppression guidance if new routing branches require casts instead of ignores.

## Source References
- `pyproject.toml:20`
- `pyproject.toml:42`
- `pyproject.toml:61`
- `pyproject.toml:73`
- `CONTRIBUTING.md:38`
- `.github/workflows/unit-tests.yml:1`
- `typings/msgpack/__init__.pyi:1`
- `typings/resonate/__init__.pyi:5`
- `src/session/manager.py:45`
- `src/subprocess/namespace.py:23`
- `src/protocol/messages.py:77`
- `src/integration/types.py:6`
- `src/subprocess/executor.py:92`
- `src/subprocess/executor.py:239`
- `src/subprocess/worker.py:514`
- `src/integration/resonate_functions.py:27`
