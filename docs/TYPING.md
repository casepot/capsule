# Typing Configuration and Guidelines

This repo enforces strong typing with mypy and basedpyright. The goals are early defect
detection, safer refactors, and clearer contracts across module boundaries.

## Tools

- mypy (strict) with Pydantic v2 plugin enabled (warn_untyped_fields = true)
- basedpyright (strict) with strict inference settings; unknown-type diagnostics as warnings

## Configuration Highlights

- mypy
  - Strict mode plus: disallow_any_generics, disallow_subclassing_any, no_implicit_reexport,
    warn_unreachable, strict_equality, show_error_codes, pretty output.
  - Pydantic v2 plugin (warn_untyped_fields = true) improves model field/type inference.
  - Local stubs resolved via `mypy_path = ["typings"]`.
  - Third‑party posture:
    - msgpack: no upstream stubs; minimal local stub provided in `typings/msgpack/__init__.pyi`.
    - dill: no upstream stubs; kept ignored for missing types (acceptable warning surface).
    - psutil, aiofiles: stubs installed (`types-psutil`, `types-aiofiles`).

- basedpyright
  - `typeCheckingMode = strict` with strict list/dict/set inference; `useLibraryCodeForTypes = true`.
  - Unknown type diagnostics enabled as warnings to highlight gaps without blocking builds.
  - Local stubs via `extraPaths = ["typings"]`.

## Local Stubs

- `typings/msgpack/__init__.pyi`: Accurate signatures for `packb` and `unpackb` used in this repo.
- `typings/resonate/__init__.pyi`: Minimal surface used by our integration code (promises registry,
  `register`, `set_dependency`, `local()`) to avoid site‑package type complexity.

## Conventions & Decisions

- Prefer precise param/return annotations for public functions and methods.
- Avoid `Any` where possible; use `Protocol`, `TypedDict`, or generics to model contracts.
- For third‑party APIs with missing types, add minimal local stubs rather than suppressing diagnostics.
- Use `cast()` sparingly; prefer type‑narrowing via `isinstance` or structural checks.

### Dynamic Namespace Policy

- Namespace values are intentionally dynamic (`Dict[str, Any]`).
- We annotate transient/auxiliary dicts (e.g., `changes`, `snapshot`, `serializable`) to avoid Unknown
  propagation, but we do NOT over‑constrain the core namespace mapping to avoid false confidence.

### Durable Function Contracts

- Durable functions are generator‑based. We type them as `Generator[Any, Any, T]` where `T` is the final
  return payload.
- Introduced `DurableResult` (`result: Any`, `execution_id: str`) to document the final payload of
  `durable_execute`, keeping `result` as `Any` (not guaranteed to be JSON‑serializable).

## Running Type Checks

```
uv run mypy src/
uv run basedpyright src/
```

## Adding New Dependencies

- Prefer libraries with `py.typed`. If missing and widely used, add `types-<package>` stubs when available.
- If no official stubs exist, add a minimal local stub under `typings/` for the subset you use.
