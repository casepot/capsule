# Providers & Capability Surface

> Status: Authoritative reference for capability providers and upcoming surfaces (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if code has drifted, double-check the current sources on your working commit, capture differences that affect your task, and raise any doc gaps to the user while you proceed with up-to-date information).

## Purpose
**Today** – Capsule exposes a single promise-backed provider: the HITL input capability registered via Resonate dependency injection (`src/integration/resonate_init.py:64`). The provider constructs protocol `InputMessage` envelopes, proxies them through the session-owned transport, and resolves user input as plain strings (`src/integration/capability_input.py:13`).

**Planned** – The roadmap adds a generalized capability registry and security policy so only approved provider wrappers are injected into the execution namespace (CAP-010, #30). Once registry wiring exists, the HTTP, Files, and Shell providers (PROV-010/#32, PROV-011/#33, PROV-012/#34) will hang off the same surface alongside a shared provider SDK (PROV-020/#42).

## Architecture Overview
- **DI & session wiring** – `initialize_resonate_local` registers durable functions, shares a `NamespaceManager`, and installs the `ResonateProtocolBridge` plus provider closures on the Resonate instance while preserving the session as the sole transport reader (`src/integration/resonate_init.py:24`, `src/integration/resonate_init.py:48`, `src/integration/resonate_init.py:74`). Input support is injected by setting an `input_capability` dependency that instantiates `InputCapability` on demand (`src/integration/resonate_init.py:64`).
- **Bridge orchestration** – The bridge creates deterministic promise ids, records pending correlation keys under an asyncio lock, applies a default 60-second guard when the caller omits timeouts, and funnels all requests back through `session.send_message` so no additional readers are introduced (`src/integration/resonate_bridge.py:32`, `src/integration/resonate_bridge.py:88`, `src/integration/resonate_bridge.py:103`, `src/integration/resonate_bridge.py:112`, `src/integration/resonate_bridge.py:127`). Responses are serialized to JSON and resolved or rejected on the stored promise, cancelling any outstanding timeout task to avoid double settlements (`src/integration/resonate_bridge.py:132`, `src/integration/resonate_bridge.py:139`, `src/integration/resonate_bridge.py:149`, `src/integration/resonate_bridge.py:166`).
- **Capability execution path** – `InputCapability.request_input` issues a UUID request id, sets a 300-second timeout, awaits the bridge-created promise, and deserializes the payload while tolerating older `{ "input": … }` shapes (`src/integration/capability_input.py:22`, `src/integration/capability_input.py:32`, `src/integration/capability_input.py:34`). Unit tests confirm the round-trip wiring and prompt creation of the bridge request (`tests/unit/test_input_capability.py:7`).
- **What is missing** – There is no general registry or namespace injection logic beyond the hard-coded `input_capability` dependency (`src/integration/resonate_init.py:64`). Capability request/response message types do not yet exist, so providers must rely on execute/input framing until PROTO-011/PROTO-012 wire negotiated hello/ack flows and idempotent capability messages (#36, #37).

## Security & Policy Controls
**Current safeguards** – Input requests run with a fixed 300-second timeout and return raw strings without additional policy enforcement (`src/integration/capability_input.py:22`). The bridge enforces a best-effort 60-second fallback to guarantee pending correlations eventually reject, but it has no audit logging, allowlists, or structured shutdown handling today (`src/integration/resonate_bridge.py:112`, `src/integration/resonate_bridge.py:203`, `src/integration/resonate_bridge.py:247`).

**Planned hardening** –
- CAP-010 (#30) introduces a deny-by-default `CapabilityRegistry` plus `SecurityPolicy` scopes, ensuring wrappers expose only capabilities authorized for the current session and that audit logs capture allow/deny decisions.
- BRIDGE-010 (#35) adds lifecycle hooks, shutdown rejection payloads, and bridge metrics so pending requests are rejected deterministically during teardown instead of idling until timeout.
- CAP-011 (#52) depends on the lifecycle work to map timeout and shutdown rejections onto Python `TimeoutError`/`EOFError` exceptions inside `InputCapability`, addressing the current bare `await promise.result()` behaviour (`src/integration/capability_input.py:32`).
- Each provider proposal carries strict resource caps: host allowlists, redirect and body limits for HTTP (#32); normalized path allowlists and per-call byte caps for Files (#33); and command allowlists plus timeouts/output truncation for Shell (#34).

## Provider Implementations
**Current coverage** – Only the Input provider ships in-repo; it transforms the promise payload into a string and ignores Resonate rejection semantics (`src/integration/capability_input.py:32`). No modules live under `src/providers/` yet, so all non-input capabilities remain future work.

**Planned surfaces** –
1. **HTTP (`caps.http.fetch`)** – Runs out of process with strict host allowlists, body size caps, redirect limits, and structured responses (PROV-010, #32). Depends on capability request messages and idempotency caching (#37).
2. **Files (`caps.files.{read,write,list}`)** – Enforces normalized path allowlists, traversal protection, and per-call byte caps with chunked transfers (PROV-011, #33). Requires security scopes from CAP-010 (#30).
3. **Shell (`caps.shell.run`)** – Executes allowlisted commands with sanitized environment, cwd restrictions, aggressive timeouts, and stdout/stderr truncation (PROV-012, #34). Shares the policy surface delivered by CAP-010 (#30).

All three providers will ship as separate modules under `src/providers/`, exposing Pydantic-modeled request/response schemas and using the bridge/transport path established by the input capability (#32, #33, #34).

## Provider SDK & Contract Tests
**Current state** – Capsule has no official provider SDK or contract harness; the bridge and input capability are wired manually via Resonate dependencies (`src/integration/resonate_init.py:64`).

**Upcoming work** – PROV-020 (#42) delivers a lightweight `capsule-provider-sdk` with an `@on_request` decorator, heartbeat helpers, and JSON-schema-backed request/response models, plus a `capsule.testing.assert_provider_contract()` suite covering retries, malformed payloads, and timeout behaviour. This SDK will become the canonical integration point once the registry and provider modules exist.

## Known Gaps & Future Work
- Bridge lifecycle, metrics, and shutdown semantics remain outstanding until BRIDGE-010 (#35) lands. Without that work, pending capability requests linger and metrics surfaces stay empty.
- Capability protocol extensions (Hello/Ack negotiation and CapabilityRequest/Response messages) are prerequisites for production-grade providers; both PROTO-011 (#36) and PROTO-012 (#37) are open.
- Input capability error mapping and EOF semantics rely on CAP-011 (#52); until then callers must handle opaque promise rejections.
- Priority routing and interceptor quarantine (BRIDGE-011, #38) will be needed to keep capability traffic from delaying cancels once high-volume providers ship.

## Source References
- `src/integration/resonate_init.py:24`
- `src/integration/resonate_bridge.py:32`
- `src/integration/capability_input.py:13`
- `tests/unit/test_input_capability.py:7`

## Legacy Material to Supersede
Replace historical provider narratives in `docs/_legacy/async_capability_prompts/current/23_spec_capability_system.md` once CAP-010 lands; the legacy spec predates the modern bridge and lacks the policy/registry contracts described above. Fold those details into this guide (or a dedicated provider API reference) as the workstream ships.

## Open Tasks
- Implement the capability registry and security policy (CAP-010, #30).
- Finalize bridge lifecycle, metrics, and structured shutdown rejections (BRIDGE-010, #35).
- Align input capability error semantics with bridge lifecycle (CAP-011, #52).
- Deliver capability negotiation and idempotent request messages (PROTO-011/#36, PROTO-012/#37).
- Ship HTTP, Files, and Shell providers under the new registry (PROV-010/#32, PROV-011/#33, PROV-012/#34).
- Publish the provider SDK plus contract harness (PROV-020, #42).
