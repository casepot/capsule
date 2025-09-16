---
name: Feature / Refactor / Hardening
about: Propose a feature, refactor, or hardening change with clear scope and invariants
title: "<WORKSTREAM>-NNN — <concise action>"
labels: []
assignees: []
---

<!--
Source of truth for structure & invariants:
  docs/issue-conventions.md
Source of truth for typing policy and stubs:
  docs/typing-guidelines.md
Use this skeleton and link to the conventions doc instead of duplicating guidance here.
Fill every section concisely; prefer bullets; add labels (type, touches, risk, rollout:flagged).
-->

## TL;DR
- 

## Background / Problem
- 

## Scope (In / Out)
- In:
- Out:

## Design Direction
- Approach and key decisions (files/components).
- Env flags + defaults (names + expected defaults).

## Affected Paths
- src/.../...
- src/.../...

## Core Invariants
- See docs/issue-conventions.md#workstream-core-invariants and list those relevant here.

## Observability
- Metrics / logs (incl. warn-once policy). Keep counters minimal; add key histograms/HWM where useful.
- Redaction policy (if applicable).

## Test Plan
- Unit:
- Integration / E2E:
- Event-driven sync (no sleeps). Include filenames/fixtures.

## Acceptance Criteria
- 

## Dependencies & Rollout
- Depends on: #
- Rollout: <flag name> (default OFF)

## Risks & Mitigations
- 

## Docs
- Specs/API/changelog to update:
