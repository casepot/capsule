TL;DR
- Provide safe introspection capabilities: list pending promises, get namespace summary (sizes/types only), and get pool status. Gate by policy and redact sensitive data.

Background / Problem
- Operators need to inspect state without injecting code or exposing objects directly.

Scope (In) / Non‑Goals (Out)
- In: caps.diagnostics.list_pending_promises(), caps.session.get_namespace_summary(), caps.pool.get_status(); redaction policy and guards.
- Out: raw object access or mutating administrative commands.

Design Direction
- Keep return values metadata-only; avoid returning live objects; integrate with Session.info() and SessionPool.get_info().

Security
- Policy-gated; redact paths/ids if configured; avoid sensitive payloads.

Test Plan
- Large namespace summaries handled; denial by policy; redaction behavior validated.

Acceptance Criteria
- Introspection available when allowed; safe and useful metadata returned; tests pass.

Implementation Notes (repo‑specific)
- Wire getters in session/pool (manager.get_info(), pool.get_info()) and bridge; expose wrappers via B1 registry under caps.diagnostics, caps.session, caps.pool.

Open Questions
- Should we include a snapshot of bridge metrics here or rely on Session.info() only?

