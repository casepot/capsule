# Issue Conventions

This document standardizes how we write and manage issues across workstreams. The goal is fast triage, clear ownership, safe rollouts, and predictable outcomes.

## Purpose
- Make ownership, risks, sequencing, and acceptance criteria obvious.
- Enable useful dashboards/search via consistent titles, labels, and sections.
- Preserve core invariants (ordering, single-reader, namespace merge-only, etc.).

## Scope
- Applies to all issues across these milestones:
  - Executor & Worker (EW) — Native Async, Pump, Messaging
  - Session Pool (POOL) — Reliability, Warmup, Health
  - Protocol & Transport (PROTO) — Negotiation, Framing, Idempotency, Streams
  - Bridge & Capabilities (BRIDGE) — Lifecycle, Routing, Registry
  - Providers (PROV) — HTTP, Files, Shell, SDK
  - Observability (OBS) — Tracing & Introspection
  - Meta (META) — Issue Quality & Templates

## Milestone Naming
- Milestone titles are human-readable with the short code in parentheses, e.g.
  - "Executor & Worker (EW) — Native Async, Pump, Messaging"
- Descriptions summarize themes, e.g. "AsyncExecutor lifecycle + worker native routing; output drain/pump policies; Display/Progress message UX."

## Issue Titles
- Format: `<WORKSTREAM>-NNN — Descriptive action`
  - Example: `EW-010 — Worker: Route TLA/async-def to AsyncExecutor (delegate blocking sync)`
- Avoid code-only titles — lists should be readable without expanding the issue.

## Labels
- Ownership `touches:*`:
  - `touches:worker`, `touches:executor`, `touches:session`, `touches:pool`, `touches:protocol`, `touches:transport`, `touches:bridge`, `touches:capability-registry`, `touches:providers`, `touches:diagnostics`, `touches:integration`.
- Risk `risk:*`:
  - `risk:ordering`, `risk:single-reader`, `risk:compat`, `risk:perf`, `risk:security`.
- Type `type:*`:
  - `type:feature`, `type:refactor`, `type:hardening`, `type:docs`, `type:test`, `type:process`.
- Rollout `rollout:*`:
  - `rollout:flagged`, `rollout:alpha`.
- Optional sequencing helpers:
  - Use a "Depends on:" body section or helper labels like `depends-on:#` / `blocks:#` (body section preferred for clarity).

## Required Issue Body Sections
Use these sections (our templates include them):

1) TL;DR
- 1–3 lines describing the action and scope.

2) Background / Problem
- Why this matters; what is limited/incorrect today.

3) Scope (In / Out)
- Boundaries to avoid scope creep.

4) Design Direction
- High-level approach, key decisions, and any env knobs + defaults.

5) Affected Paths
- Canonical paths only, one per line (e.g., `src/protocol/messages.py`).

6) Core Invariants
- Workstream-relevant guardrails (see reference list below).

7) Observability
- Metrics/logs; warn-once policies; redaction policy where applicable.

8) Test Plan
- Unit/integration/e2e + filenames; prefer event-driven waits (no sleeps).

9) Acceptance Criteria
- Verifiable outcomes (behavior and validation), not just "merged".

10) Dependencies & Rollout
- `Depends on: #...` and any flags; add `rollout:flagged` label if gated.

11) Risks & Mitigations
- What could go wrong and how you’re preventing it.

12) Docs
- Specs/API/changelog to update.

### Minimal issue body template (copyable)

```
TL;DR
- <1–3 lines>

Background / Problem
- <context>

Scope (In / Out)
- In: <...>
- Out: <...>

Design Direction
- <approach, env flags + defaults>

Affected Paths
- src/.../...
- src/.../...

Core Invariants
- <invariants to preserve>

Observability
- <metrics/logs; warn-once; redaction>

Test Plan
- <unit/integration/e2e + filenames; event-driven waits>

Acceptance Criteria
- <verifiable outcomes>

Dependencies & Rollout
- Depends on: #...
- Rollout: <flag name> (default OFF)

Risks & Mitigations
- <risks + mitigations>

Docs
- <specs/API/changelog to update>
```

## Workstream Core Invariants (reference)

### Executor & Worker (EW)
- Single-reader invariant (Session is the only transport reader).
- Output-before-result ordering (worker drains outputs before ResultMessage; worker strict on drain timeout).
- Merge-only namespace updates (preserve `ENGINE_INTERNALS` keys; no replacement of the namespace dict).
- Pump-only stdout/stderr (no direct writes except narrowly-scoped emergency logs if unavoidable).
- No event loop creation in durable layers (loops are owned by executor/transport).

### Protocol & Transport (PROTO)
- Framing integrity; bounded frame sizes.
- Ack-before-result ordering (when Ack is present).
- Idempotency correctness (keys, cache policy).
- Event-driven (no polling) for readers/buffers.

### Session Pool (POOL)
- No await while holding locks.
- Event-driven warmup (signals over polling).
- Hybrid health check (timer baseline + event triggers).
- Circuit breaker to avoid thundering herds.

### Bridge & Capabilities (BRIDGE)
- Single-reader invariant.
- Deterministic correlation.
- Passive interceptors; quarantine budgets and fairness (no data-path starvation).
- Prompt shutdown rejection for pending correlations.

### Providers (PROV)
- Strict allowlists; size/time caps; structured observability.
- Out-of-process execution (no in-process provider code execution).

### Observability (OBS)
- Bounded memory.
- Metadata-only introspection; redaction policy.
- No additional transport readers.

## Rollout & Env Flags
- Describe flags + defaults in Design Direction and Rollout sections.
- Naming guidance:
  - Worker: `WORKER_*` (e.g., `WORKER_ENABLE_NATIVE_ASYNC`).
  - AsyncExecutor: `ASYNC_EXECUTOR_*` (e.g., `ASYNC_EXECUTOR_AST_CACHE_SIZE`).
  - Protocol/Providers: `CAPS_*` acceptable, but prefer area-specific prefixes when wiring to code.
- Precedence: constructor args > env.

## Duplicates & Consolidation
- Close duplicates with a short comment linking the canonical issue (e.g., "Closed as duplicate of #NN").
- Prefer the newer, more complete issue as canonical.

## Quality Checklist (on creation/edit)
- [ ] Title follows pattern; milestone assigned.
- [ ] Labels applied: touches, type, risk; rollout if flagged.
- [ ] All required sections filled; Affected Paths canonical; Core Invariants listed.
- [ ] Dependencies cross-linked; acceptance criteria testable.
- [ ] Docs to update identified.

## Examples (real patterns)
- EW-010 — Worker routes async code to AsyncExecutor under a flag; preserves output-before-result and single-reader; depends on lifecycle/plumbing; worker remains strict on drain timeouts.
- PROTO-010 — FrameBuffer switches to asyncio.Condition to eliminate polling; reduce idle CPU; maintain framing invariants.
- BRIDGE-010 — Bridge lifecycle exposes metrics via Session.info(); close/cancel_all is idempotent; pending rejected on shutdown.

