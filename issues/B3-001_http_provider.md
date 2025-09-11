TL;DR
- Ship an out-of-process HTTP provider exposing caps.http.fetch with strict host allowlist, size/time caps, and structured responses.

Background / Problem
- We need a reference network provider with constrained security to exercise the capability system and support common tasks.

Scope (In) / Non‑Goals (Out)
- In: provider process; request/response schema; allowlist policy; redirects cap; timeouts; basic retries.
- Out: auth/secrets management beyond provider config; streaming responses (can integrate later with B2).

Design Direction
- Provider runs as a separate process with a small RPC surface (JSON/msgpack). The caps.http.fetch wrapper validates inputs and sends CapabilityRequestMessage through the bridge/transport.
- Enforce host/path allowlists in provider before making requests; cap body sizes and redirect depth.

Contract (user space)
```py
resp = await caps.http.fetch(
    url="https://api.example.com/data",
    method="GET",
    headers={"Accept": "application/json"},
    body=None,
    timeout_ms=5000,
)
data = resp.json()  # or resp.text/resp.bytes
```

Policy & Config
- CAPS_HTTP_ALLOWED_HOSTS: list[str]
- CAPS_HTTP_MAX_BODY_BYTES: int (default 5 MiB)
- CAPS_HTTP_REDIRECTS_MAX: int (default 3)

Observability
- Metrics: latency histograms, error codes, bytes received
- Logs: redacted headers; blocked requests

Security
- Strict allowlist; sanitize headers; forbid local network by default unless explicitly allowed.

Compatibility
- Additive provider; capability wrapper injected via B1 registry.

Test Plan
- Allow/deny host behavior; redirect handling; large body truncation; timeout; negative security cases.

Acceptance Criteria
- Allowed host works; disallowed host is blocked with structured error; metrics emitted.

Implementation Notes (repo‑specific)
- New module: src/providers/httpd/* (process entrypoint + handler). Use Pydantic for request/response models in the provider.
- Wrapper added by B1 registry as caps.http.fetch using @validate_call (once available) or explicit validation.

Open Questions
- Use AnyHttpUrl to allow localhost/IPs in dev by policy?

