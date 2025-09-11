TL;DR
- Introduce a CapabilityRegistry and SecurityPolicy to define, inject, and gate namespaced caps.* wrappers in user space. Deny-by-default. Keep the core small and auditable.

Background / Problem
- We need a formal way to define capabilities and inject only those allowed by policy. Today, some integration code exists for durable input; we need a general, non-bypassable mechanism.

Scope (In) / Non‑Goals (Out)
- In: registry of capability specs; security policy modeling; injection pipeline; audit logging; minimal schema validation hooks.
- Out: provider processes (handled by B3); streaming protocol (B2).

Design Direction
- Namespacing: inject as caps.<domain>.<fn> wrappers; wrappers only marshal/validate and send CapabilityRequestMessage across the bridge/transport.
- Policy: allow/deny lists with per-domain scopes (e.g., file allowlist); deny-by-default; auditable decisions.
- Types: keep specs simple (name, schema_in/out, tags) as Pydantic models to emit JSON Schema for docs.

Types / Schemas (proposed)
```py
from pydantic import BaseModel, Field

class CapabilitySpec(BaseModel):
    name: str
    schema_in: dict = Field(default_factory=dict)
    schema_out: dict = Field(default_factory=dict)
    tags: set[str] = Field(default_factory=set)

class SecurityPolicy(BaseModel):
    allow: set[str] = Field(default_factory=set)
    deny: set[str] = Field(default_factory=set)
    scopes: dict[str, dict] = Field(default_factory=dict)  # e.g., {"files": {"allowlist": ["./sandbox"]}}

class CapabilityRequestMessage(BaseModel):
    type: Literal["capability_request"] = "capability_request"
    id: str
    timestamp: float
    request_id: str
    capability: str
    payload: dict
    idempotency_key: str | None = None
    timeout_ms: int | None = None
```

Public APIs
- Registry: register(spec), inject(namespace, execution_id, policy)
- User space: await caps.files.read(path="…") etc. (wrappers emit CapabilityRequestMessage)

Invariants
- Namespaced injection only; no global pollution.
- Policy is non-bypassable; if not allowed, wrapper absent.

Error Semantics
- Disallowed capability → PolicyDeniedError; missing wrapper signals clearly.
- Payload validation errors → structured ValidationError.

Config
- CAPS_POLICY_PATH (optional)
- CAPS_CAPABILITY_DEFAULT_TIMEOUT_MS

Observability
- Metrics: capability_injected_total, policy_denied_total
- Audit log: decision records with who/what/why

Security
- Deny-by-default; no dynamic eval in wrappers; inputs schema-validated when possible.

Compatibility
- Additive; registry empty by default.

Performance Targets
- Injection overhead < 1ms/capability; wrapper call overhead negligible.

Test Plan
- Unit: allow/deny/scopes; missing wrappers; schema validation wires.
- Integration: simple session with allowed capability succeeds; disallowed fails with clear error.

Rollout
- Land registry/policy core first; examples follow.

Dependencies
- Pairs with B3 providers but not blocked by them.

Risks & Mitigations
- Over-permissive scopes → deny-by-default; audit trail.

Acceptance Criteria
- Capabilities are injected only when allowed; decisions auditable; tests pass.

Implementation Notes (repo‑specific)
- Add modules: src/capabilities/registry.py, src/security/policy.py. Wire injection at session/worker init.
- Extend src/protocol/messages.py with CapabilityRequestMessage.

Open Questions
- Policy format (JSON vs Python dict); suggest JSON for portability.

