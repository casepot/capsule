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

## Where Typing Is Deliberately Loose (and why)

We aim for strong typing everywhere, but a few boundaries remain intentionally loose. These are narrow and documented so reviewers understand why `Any` or `object` appears.

1) Dynamic execution namespace
- The session namespace is user‑authored and inherently dynamic.
- We keep it as `dict[str, Any]` to avoid false precision. Internal engine keys (e.g., `ENGINE_INTERNALS`) are typed precisely, but the merged namespace stays dynamic.

2) Capability payloads and provider I/O
- Capability request/response payloads are modeled as Pydantic models where feasible, but provider surfaces can accept heterogeneous JSON‑like data. Use a JSON alias when modeling payloads:
  - `JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]`
- Where payloads are extensible and not yet schema‑fixed, `dict[str, Any]` may appear but should be tightened to `JSONValue` or a TypedDict as contracts stabilize.

3) Diagnostics and structured logging attrs
- Trace/log attributes are intentionally flexible to avoid schema churn. Prefer `dict[str, object]` over `Any` so values remain opaque but not contagious in type inference.
- Redaction policy is orthogonal; keep types broad and enforce redaction at the call sites.

4) Executor results and user values
- User code can return any Python object. Public APIs that expose “result” values use `Any` by design. Callers are responsible for downcasting or validating.

5) Third‑party integrations without stubs
- If a widely‑used library lacks `py.typed`, we add minimal local stubs under `typings/` for the subset we call (preferred) instead of `type: ignore`. Current examples: `msgpack`, a small `resonate` surface.

6) Exception typing and cross‑thread signaling
- Cancellation and error paths sometimes bubble `BaseException`. Keep signatures broad where catching/propagation semantics require it (e.g., `except BaseException` in task cleanup); avoid narrowing to `Exception` if it changes behavior.

7) Internal stats and counters
- Counters/maps that evolve (feature flags, metrics names) may be `Mapping[str, int]` or `dict[str, int]` rather than Literals; keep write APIs narrow but allow read‑only inspection to stay generic.

Guidance: prefer `object` to contain values you don’t operate on, and reserve `Any` for values you directly manipulate where precision isn’t practical yet.

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

## Allowed Ignores and Escapes

Use escapes sparingly and document intent inline.

- `# type: ignore[<code>]  # rationale`: Include the specific error code and a short reason (e.g., upstream stub gap; TODO link to follow‑up).
- `typing.cast(T, x)`: Prefer to structural checks; acceptable for narrow interop or parsing.
- `reveal_type(...)`: Allowed in temporary debug branches; remove before merge.

Prefer fixing types at the source (add stubs, refine Protocols/TypedDicts) over sprinkling ignores.
