TL;DR
- Implement an out-of-process Files provider with read/write/list operations, normalized paths, and strict allowlists.

Background / Problem
- File IO must remain constrained and auditable; we need a provider with careful path handling and chunked transfers for large files.

Scope (In) / Non‑Goals (Out)
- In: read/write/list; path normalization; symlink resolution; traversal protection; chunked IO; policy enforcement.
- Out: recursive operations or watch APIs (future work).

Contract (user space)
```py
txt = await caps.files.read("./sandbox/data.txt")
await caps.files.write("./sandbox/out.json", data, mode="w")
files = await caps.files.list("./sandbox")
```

Policy & Config
- CAPS_FILES_ALLOWLIST: list[str] (globs/roots)
- CAPS_FILES_MAX_BYTES_PER_CALL: int (default 8 MiB)

Observability
- Metrics: bytes read/written, truncations, denied attempts
- Logs: attempted paths (normalized), denials

Security
- Normalize and resolve (realpath) before checks; deny traversals; forbid operations outside allowlist; binary-safe chunking.

Compatibility
- Additive provider; wrappers via B1 registry.

Test Plan
- Traversal attempts (../, symlink escape) are denied; large file reads chunked; writes honor caps; list scoped.

Acceptance Criteria
- Reads/writes within scope succeed; out-of-scope is denied with structured error; tests pass.

Implementation Notes (repo‑specific)
- New module: src/providers/filesd/* with Pydantic models for requests/responses; JSON/msgpack RPC.
- Wrapper arguments validated via registry; policy scopes consulted prior to dispatch.

Open Questions
- How do we express allowlist semantics (globs vs rooted prefixes) in policy?

