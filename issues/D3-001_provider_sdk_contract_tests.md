TL;DR
- Deliver a minimal capsule-provider-sdk and a capsule.testing contract harness to make provider development easy and correct.

Background / Problem
- External providers will proliferate; we need a standard SDK and a contract test suite to reduce friction and ensure compatibility.

Scope (In) / Non‑Goals (Out)
- In: SDK with Provider class and @on_request decorator; schema validation; heartbeat; discovery; contract harness.
- Out: full-featured framework; keep it minimal and focused on contracts.

SDK
- Request/response models as Pydantic BaseModel; generate JSON Schema for docs; helpers for resolve/reject and heartbeats.

Testing Harness
- capsule.testing.assert_provider_contract(url) runs canned suites: idempotency, retries, malformed inputs, timeouts, heartbeats.

Docs
- Cookbook examples and schema export instructions.

Test Plan
- Fake providers in CI; failure injection paths.

Acceptance Criteria
- Provider passes contract tests with < 30 LOC scaffolding; docs published.

Implementation Notes (repo‑specific)
- Separate package for SDK; harness lives in this repo under a testing namespace; integrate with B3 providers.

Open Questions
- Do we ship the SDK from this repo initially or split immediately?

