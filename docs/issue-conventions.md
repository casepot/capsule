# Issue Conventions

> Status: Authoritative reference for Capsule issue hygiene (sources referenced at commit `47c9d77602a8f6fb988844df4a8791ad88ebb29d`; if code has drifted, double-check the current sources on your working commit, capture differences that affect your task, and raise any doc gaps to the user while you proceed with up-to-date information).

## Purpose
Capsule invests in high-signal issue writing so maintainers can guard runtime invariants and plan safe rollouts. Issues must restate the invariants they touch—single-reader transport dispatch (`src/session/manager.py:195`), merge-only namespace setup (`src/subprocess/worker.py:137`), output-before-result drain policy (`src/subprocess/worker.py:333`), and pump-only stdout/stderr handling (`src/subprocess/executor.py:452`). `META-010 (#53)` tracks the hygiene passes that keep these expectations consistent across the backlog.

## Required Sections
The feature/refactor/hardening template enumerates the canonical headings and should stay authoritative (`.github/ISSUE_TEMPLATE/feature.md:18-59`). Fill every section with precise bullets:

- `TL;DR` — 1–3 lines capturing the action, owner, and primary risk.
- `Background / Problem` — why the current behavior is insufficient.
- `Scope (In / Out)` — explicit boundaries to prevent scope creep.
- `Design Direction` — intended approach, primary modules, and environment knobs with defaults.
- `Affected Paths` — canonical module or doc paths (`src/...`, `docs/...`).
- `Core Invariants` — enumerate the runtime invariants that must hold, referencing the relevant code or docs.
- `Observability` — metrics/log changes, warn-once policies, and redaction commitments.
- `Test Plan` — unit/integration/e2e coverage with filenames and event-driven waits.
- `Acceptance Criteria` — verifiable outcomes that prove the change landed as expected.
- `Dependencies & Rollout` — upstream blockers, feature flags, rollout order, and ownership for toggles.
- `Risks & Mitigations` — credible risks matched with specific mitigations.
- `Docs` — the documentation set that must be updated; use the mapping below for guidance.

`META` / process issues follow the same opening sections and use `Plan` for execution details plus dependencies (`.github/ISSUE_TEMPLATE/meta.md:11-32`). When feature issues warrant `Implementation Notes`, add a clearly labeled subsection after the acceptance criteria; folding that section into the template is part of the ongoing hygiene tracked in `META-010 (#53)`.

## Labeling & Metadata
Keep dashboards searchable by applying labels consistently:

- **Workstream (`area-*`)** — select the primary delivery lane (`area-exec`, `area-providers`, etc.), as demonstrated in EW-010 (#51) and PROV-010 (#32).
- **Impacted surfaces (`touches:*`)** — tag each runtime surface touched; EW-010 (#51) carries `touches:executor` and `touches:worker`, while CAP-011 (#52) adds `touches:capability-registry` alongside `touches:session` and `touches:bridge`.
- **Classification (`type:*`)** — choose among `type:feature`, `type:refactor`, `type:hardening`, `type:test`, `type:docs`, or `type:process` (e.g., META-010 (#53) uses `type:process`).
- **Risk flags (`risk:*`)** — surface ordering, single-reader, compat, perf, or security risks based on the invariants involved (EW-010 (#51) marks `risk:ordering` and `risk:single-reader`).
- **Rollout stage (`rollout:*`)** — track gated work with `rollout:flagged` or controlled previews with `rollout:alpha`; drop the label once the flag is removed (EW-010 (#51) uses `rollout:flagged`).
- **Auxiliary tags** — add `perf`, `security`, `protocol`, `needs-design-review`, `needs-security-review`, or `touches:integration` when review routing or compliance demands it (POOL-010 (#29) carries `perf`; PROTO-012 (#37) uses `protocol` and `needs-design-review`).

Avoid legacy `kind-*` labels on new issues; they remain only for historical searches.

## Dependencies & Rollout Practices
Every dependency or gate must be encoded where reviewers expect it:

- Use the `Depends on:` block in the issue body and link to each dependency; mirror critical ordering in milestone descriptions (`.github/ISSUE_TEMPLATE/feature.md:51-53`).
- Call out feature flags in both `Design Direction` and `Dependencies & Rollout`, recording the flag name, default, owning team, and clean-up plan. Keep `rollout:*` labels in sync with the body.
- When dependency chains exceed one hop, include a short bullet list summarizing the execution order (see the dependency tree already documented in EW-010 (#51)).
- Update the checklist in META-010 (#53) as dependencies close so the hygiene pass reflects reality.

## Documentation Checklist
Populate the `Docs` section with concrete filenames so documentation evolves alongside the code. Use this mapping as a baseline:

- Execution & worker changes → `docs/execution-engine.md`, `docs/async-executor.md`, and `docs/architecture-overview.md` when control-plane behavior changes.
- Session lifecycle or pooling → `docs/session-runtime.md`, `docs/session-pool.md`.
- Protocol or transport → `docs/protocol.md`.
- Bridge or capabilities → `docs/bridge-capabilities.md`.
- Observability additions → `docs/diagnostics-and-observability.md`.
- Provider features → `docs/providers.md`.
- Configuration or environment knobs → `docs/configuration-reference.md`.
- Typing or stub hygiene → `docs/typing-guidelines.md`.
- Process or template work → `docs/issue-conventions.md` and `.github/ISSUE_TEMPLATE/*`.

When an issue spans multiple areas, list every affected guide and note sequencing requirements (e.g., update `docs/protocol.md` before `docs/providers.md` if wire format changes precede provider enablement).

## Testing & Observability Expectations
Test plans must respect Capsule’s event-driven runtime. Message waits race queue consumption against cancellation without polling (`src/session/manager.py:309`), workers refuse to send results until outputs drain (`src/subprocess/worker.py:333`), and the threaded executor pumps stdout/stderr exclusively through the async queue (`src/subprocess/executor.py:452`). Reflect that in your issues by:

- Preferring events or conditions over sleeps; name fixtures and timeouts explicitly.
- Exercising cancellation paths so cancel metrics continue to increment (`src/session/manager.py:353`).
- Asserting metrics or counters that your change introduces—ThreadedExecutor already tracks queue depth and drop counts suitable for assertions (`src/subprocess/executor.py:283-305`).
- Documenting how observability surfaces (logs, metrics, traces) will be verified without adding new transport readers; heartbeat emission lives in the worker loop (`src/subprocess/worker.py:245-262`).

## Maintenance Notes
- Update this guide whenever invariants change, new documentation files land, or label taxonomies evolve; cross-check `docs/README.md` when guides are added or renamed.
- GitHub templates (`.github/ISSUE_TEMPLATE/*.md`) now point to this guide; keep them in sync whenever the structure or section list changes.
- When label sets change, refresh the examples here and raise a META issue if bulk retagging is required.
- Keep META-010 (#53) updated as workstreams refresh their backlogs so this document and the templates stay accurate.

## Known Gaps & Planned Updates
- META-010 (#53) remains in progress; it tracks refreshing POOL-010 (#29), EW-015 (#27), EW-016 (#28), and provider issues #32–#34/#42 so they match the required sections.
- Provider and capability workstreams still owe observability/test details; once those issues are rewritten, confirm `docs/providers.md` and `docs/bridge-capabilities.md` capture the new policies.

## Legacy Material Superseded
- `docs/_legacy/PROCESS/ISSUE_CONVENTIONS.md`
