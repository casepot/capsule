# Issue Template (General)

<!--
How to use this template

- Read docs/issue-conventions.md for required sections, titles, labels, and invariants.
- Keep sections concise but complete; prefer bullets over prose. Fill every section.
- Add labels on creation: `type:*`, `touches:*`, and any `risk:*`; add `rollout:flagged` if behind a flag.
- Cross-link dependencies in “Dependencies & Rollout” (e.g., Depends on: #36; Blocks: #40) and related issues.
- Name tests and prefer event-driven sync (no sleeps); include filenames/fixtures in Test Plan.
- List “Affected Paths” with canonical file paths only.
- Preserve core invariants for your workstream (see reference in docs/issue-conventions.md).

You can paste this body into existing issues when doing quality passes (e.g., via `gh issue edit`).
-->

## TL;DR
- 1–3 lines describing the action and narrow scope.

## Background / Problem
- Why this matters; what is limited/incorrect today; links to prior patterns or regressions.

## Scope (In / Out)
- In:
- Out:

## Design Direction
- Approach and key decisions; keep it specific (files/components touched).
- Env flags and defaults (names + expected defaults).

## Affected Paths
- src/.../...
- tests/.../...

## Core Invariants
- List the guardrails relevant to this work (e.g., single-reader transport; output-before-result; merge-only namespace; no polling; event loop ownership; pump-only outputs).

## Observability
- Metrics: minimal counters + key histograms (include HWM if useful).
- Logs: rate-limit; warn-once per execution or state change; redaction policy where applicable.

## Test Plan
- Unit:
- Integration / E2E:
- Event-driven sync (no sleeps). Include test filenames and fixtures.

## Acceptance Criteria
- Verifiable outcomes (behavior + validation), not just “merged”.

## Implementation Notes (repo-specific)
- Call out local patterns or files that require special care (e.g., session/worker env wiring; transport ordering; executor pump policies).

## Dependencies & Rollout
- Depends on: #
- Rollout: <flag name> (default OFF) and order-of-operations if relevant.

## Risks & Mitigations
- Risk:
  - Mitigation:

## Docs
- Specs/API/changelog to update; links to any diagrams or cookbook examples.

---

### Quality Checklist (maintainers)
- [ ] Title follows `<WORKSTREAM>-NNN — <action>`; milestone assigned
- [ ] Labels applied: `type:*`, `touches:*`, `risk:*`, and `rollout:*` if flagged
- [ ] All sections filled; Affected Paths canonical; Core Invariants listed
- [ ] Dependencies cross-linked; Acceptance Criteria are testable
- [ ] Docs updates identified

### References
- Conventions: `docs/issue-conventions.md`
- PR template: `.github/PULL_REQUEST_TEMPLATE.md`
- Issue templates: `.github/ISSUE_TEMPLATE/`
