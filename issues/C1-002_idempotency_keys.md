TL;DR
- Add optional idempotency_key to CapabilityRequestMessage and cache successful results per (capability, idempotency_key, session) with TTL/LRU.

Background / Problem
- Retrying requests the provider may have processed can cause duplicate effects; idempotency keys allow safe retries.

Scope (In) / Non‑Goals (Out)
- In: request field; bridge/session-side cache; metrics and TTL/LRU management; clear semantics.
- Out: cross-session/global idempotency store (future option).

Design Direction
- Cache only successful results by default; consider configurable policy for error caching.
- On duplicate (capability, key), return cached result without invoking provider.

Config
- CAPS_IDEMP_TTL_SEC (default: 600)
- CAPS_IDEMP_CACHE_MAX (default: 10k entries)

Observability
- Metrics: idempotency_hits_total, idempotency_evictions_total

Test Plan
- Replay returns cached result; TTL expiry and LRU eviction behave as expected; optional policy for error caching.

Acceptance Criteria
- Idempotency resolves duplicate requests without re-invoking provider; tests pass.

Implementation Notes (repo‑specific)
- Extend CapabilityRequestMessage (B1) and add a small cache in the bridge layer (e.g., src/integration/resonate_bridge.py or a new bridge cache helper).

Open Questions
- Cache success-only vs include certain error classes?

