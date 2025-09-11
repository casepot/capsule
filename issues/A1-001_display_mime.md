TL;DR
- Introduce a first‑class DisplayMessage that carries MIME bundles (text/html, image/png, etc.) with chunking and strict Display-before-Result ordering. Add a worker display hook and optional caps.display helpers. Keep it additive and behind a flag.

Background / Problem
- Rich outputs are currently represented only as stdout text; there is no structured message for rendering or progressive updates.
- Large payloads (plots, HTML, images) risk exceeding frame limits; we need chunking and caps to avoid DoS.
- We already enforce output-before-result ordering (tests/features/test_output.py); extend that to structured displays and keep deterministic ordering per execution.

Scope (In) / Non‑Goals (Out)
- In: new DisplayMessage type; base64 or framed-binary chunking; worker-side repr collection; ordering semantics in Session.execute; optional display_id for updates; counters and size histograms; feature flag and size caps.
- Out: advanced client layouting, GUI frameworks, provider-driven rich UIs (tracked elsewhere under streams/providers).

Design Direction (constraints, not prescription)
- Message shape: a dataclass-like Pydantic model aligned with the repo’s message style in src/protocol/messages.py.
- Transport: continue to use msgpack framing (src/protocol/transport.py); for bytes, use msgpack bin type; if JSON fallback is used, base64 encode.
- Ordering: Session.execute already yields Output before Result/Error; extend queue routing to ensure all Display for a given execution_id are yielded before terminal messages.
- Chunking: respect frame limits; carry seq and more fields; reassembly keyed by (display_id, seq) or per-execution seq.
- Feature flag: enable in dev, off in CI.

Types / Schemas (proposed)
```py
from typing import Literal
from pydantic import BaseModel, Field

class DisplayMessage(BaseModel):
    type: Literal["display"] = Field(default="display")
    id: str
    timestamp: float
    execution_id: str
    display_id: str | None = None
    mime_bundle: dict[str, bytes | str]
    seq: int
    more: bool = False
```

Public APIs (user space)
- Implicit: worker extracts _repr_* and emits DisplayMessage.
- Optional shim (until B1 lands): caps.display.html("<div>…</div>") and caps.display.png(b"…") -> enqueues DisplayMessage.

Invariants
- For a given execution_id, all DisplayMessage arrive before Result or Error.
- Single reader invariant remains: Session is the sole transport reader.
- Size caps and chunking are enforced; oversize payloads are truncated with notice.

Error Semantics
- Serialization failure for one mime key -> drop that key and log a warning; continue with others.
- Oversize -> truncate + add diagnostic attribute (e.g., truncated: true, original_size: n).

Config Knobs
- CAPS_ENABLE_DISPLAY: bool (default: 1 in dev, 0 in CI)
- CAPS_MAX_DISPLAY_MB: int (default: 8)
- CAPS_DISPLAY_CHUNK_KB: int (default: 128)

Observability
- Metrics: display_messages_total, display_bytes_total, display_chunks_total, display_truncated_total
- Logs: execution_id, display_id, mime keys, sizes

Security
- Treat payload as data only; document client-side sandboxing for HTML.

Compatibility
- Additive protocol; consumers ignoring type=="display" continue to work.

Performance Targets
- Display-off overhead ~0–2% per execution.
- Chunking throughput ≥ 10 MB/s intra-process.

Test Plan
- Unit: repr collection order and bundle formation; chunk boundaries; seq/more continuity.
- Property: Display-before-Result ordering under concurrency (extend existing output tests).
- Negative: oversize truncation; invalid mime key; bytes vs str values round-trip via msgpack.
- Load: 100 large displays with chunking; verify routing does not starve.

Rollout
- Ship behind CAPS_ENABLE_DISPLAY; default off in CI.

Dependencies
- Relies on current bounded routing semantics and lifecycle wiring already present in Session manager; no hard code deps.

Risks & Mitigations
- Payload pressure/DoS → size caps, chunking, counters, and truncation policy.

Acceptance Criteria
- Structured DisplayMessage visible in client; ordering enforced; size caps working; tests added and pass.

Implementation Notes (repo‑specific)
- Files to touch: src/protocol/messages.py, src/subprocess/worker.py, src/session/manager.py, src/protocol/framing.py (chunk helper), src/session/config.py.
- Keep message creation via Pydantic BaseModel to match existing messages.

Open Questions
- Start with msgpack bytes for binary payloads and avoid base64 unless JSON mode is used?
- Do we want a stable display_id for progressive updates by default?

